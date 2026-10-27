import random

from fastype.engine import TypingSession
from fastype.store import Store, weakness_scores
from fastype import texts


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def type_text(s, clock, text, dt=0.2):
    for ch in text:
        s.type_char(ch)
        clock.t += dt


def test_perfect_run():
    clock = FakeClock()
    s = TypingSession("hello world", clock=clock)
    type_text(s, clock, "hello world")
    assert s.finished
    r = s.result()
    assert r.accuracy == 100.0
    assert r.errors == 0
    # 11 chars, 10 gaps of 0.2s = 2s; 11/5 words in 2/60 min = 66 wpm
    assert round(r.wpm) == 66
    assert r.consistency == 100.0


def test_errors_and_backspace():
    clock = FakeClock()
    s = TypingSession("cat", clock=clock)
    type_text(s, clock, "cx")
    s.backspace()
    type_text(s, clock, "at")
    assert s.finished
    r = s.result()
    assert r.errors == 1
    assert r.key_stats["a"].misses == 1 and r.key_stats["a"].hits == 1
    assert r.accuracy == 75.0


def test_word_backspace():
    clock = FakeClock()
    s = TypingSession("one two", clock=clock)
    type_text(s, clock, "one tw")
    s.backspace(word=True)
    assert "".join(c for c, _ in s.typed) == "one "


def test_time_limit():
    clock = FakeClock()
    s = TypingSession("a" * 100, time_limit=1.0, clock=clock)
    type_text(s, clock, "aaaaaaa", dt=0.25)
    assert s.finished
    assert s.elapsed() == 1.0
    assert s.position == 4  # the 5th key arrived as time ran out


def test_auto_indent():
    clock = FakeClock()
    target = "if x:\n    y"
    s = TypingSession(target, auto_indent=True, clock=clock)
    type_text(s, clock, "if x:\n")
    assert s.position == len("if x:\n    ")
    s.backspace()  # removes indentation together with the newline
    assert s.position == len("if x:")
    type_text(s, clock, "\ny")
    assert s.finished
    assert s.result().chars_typed == 8  # indentation not counted


def test_store_roundtrip_and_weakness():
    clock = FakeClock()
    s = TypingSession("abab" * 5, clock=clock)
    type_text(s, clock, "abxb" * 5)
    store = Store(":memory:")
    store.save("words", s.result())
    store.save("words", s.result())
    stats = store.key_stats()
    assert stats["a"].misses == 10
    assert store.summary()["sessions"] == 2
    scores = weakness_scores(stats)
    assert scores["a"] > scores["b"]


def test_weighted_words_prefer_weak_letters():
    rng = random.Random(1)
    text = texts.words(400, weights={"z": 50.0, "q": 50.0}, rng=rng)
    plain = texts.words(400, rng=random.Random(1))
    assert text.count("q") + text.count("z") > plain.count("q") + plain.count("z")


def test_punctuation_ends_sentence():
    text = texts.words(30, punctuation=True, rng=random.Random(3))
    assert text[0].isupper() and text[-1] in ".?!"


def test_word_lists_load_without_duplicates():
    for lang in texts.LANGUAGES:
        words = texts.word_list(lang)
        assert len(words) > 2000
        assert len(words) == len(set(words))


def test_tiers_limit_the_pool():
    rng = random.Random(4)
    top = set(texts.word_list("English")[:200])
    assert set(texts.words(300, tier="top 200", rng=rng).split()) <= top
    wide = set(texts.words(2000, tier="all", rng=rng).split())
    assert wide - set(texts.word_list("English")[:1000])  # reaches past the top 1k


def test_common_words_come_up_more_often():
    text = texts.words(5000, tier="all", rng=random.Random(5)).split()
    ranks = {w: i for i, w in enumerate(texts.word_list("English"))}
    top100 = sum(1 for w in text if ranks[w] < 100)
    last100 = sum(1 for w in text if ranks[w] >= len(ranks) - 100)
    assert top100 > 2 * last100


def test_german_keeps_capitals():
    assert "Haus" in texts.word_list("German") and "haus" not in texts.word_list("German")
