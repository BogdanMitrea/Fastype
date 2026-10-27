"""Practice text generators."""
from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent / "data"
LANGUAGES = {"English": "english.txt", "German": "german.txt"}
# Difficulty tiers: how far down the frequency-ordered list words are drawn from.
TIERS = {"top 200": 200, "top 1k": 1000, "all": None}


@lru_cache(maxsize=None)
def word_list(language: str) -> list[str]:
    """The language's words, most common first (duplicates dropped)."""
    words: dict[str, None] = {}
    for line in (DATA / LANGUAGES[language]).read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            words.update(dict.fromkeys(line.split()))
    return list(words)


@lru_cache(maxsize=None)
def _frequency_weights(size: int) -> list[float]:
    """Common words come up more often: weight falls off with rank, like real text."""
    return [1.0 / (rank + 25) ** 0.6 for rank in range(size)]


PUNCT_END = [".", ".", ".", "?", "!"]
PUNCT_MID = [",", ",", ";", ":"]

CODE_SNIPPETS = [
    '''def fizzbuzz(n):
    for i in range(1, n + 1):
        if i % 15 == 0:
            print("FizzBuzz")
        elif i % 3 == 0:
            print("Fizz")
        else:
            print(i)''',
    '''class Stack:
    def __init__(self):
        self.items = []

    def push(self, item):
        self.items.append(item)

    def pop(self):
        return self.items.pop()''',
    '''squares = {n: n ** 2 for n in range(10) if n % 2}
names = [p["name"].title() for p in people]
total = sum(x * y for x, y in zip(prices, counts))''',
    '''with open(path, "r", encoding="utf-8") as f:
    for line_no, line in enumerate(f, start=1):
        if line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        config[key.strip()] = value.strip()''',
    '''#include <vector>
#include <iostream>

int main() {
    std::vector<int> v{3, 1, 4, 1, 5};
    for (auto& x : v) {
        x *= 2;
    }
    std::cout << v[0] << "\\n";
    return 0;
}''',
    '''async def fetch_all(urls):
    async with aiohttp.ClientSession() as s:
        tasks = [s.get(u) for u in urls]
        return await asyncio.gather(*tasks)''',
    '''template <typename T>
T clamp(T value, T lo, T hi) {
    return value < lo ? lo : (hi < value ? hi : value);
}''',
    '''SELECT name, COUNT(*) AS orders
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE o.created_at >= '2026-01-01'
GROUP BY name
ORDER BY orders DESC;''',
]

def words(
    count: int,
    language: str = "English",
    punctuation: bool = False,
    numbers: bool = False,
    weights: Optional[dict[str, float]] = None,
    rng: Optional[random.Random] = None,
    tier: str = "top 1k",
) -> str:
    """Generate `count` random words separated by spaces.

    Words come from the first N of the language's list (see TIERS), with common words
    picked more often. With `weights` (a score per character, higher = needs more
    practice), words containing weak characters are picked more often still.
    """
    rng = rng or random.Random()
    pool = word_list(language)[:TIERS[tier]]
    word_weights = _frequency_weights(len(pool))
    if weights:
        word_weights = [f * (1.0 + sum(weights.get(c.lower(), 0.0) for c in set(w)))
                        for f, w in zip(word_weights, pool)]

    out: list[str] = []
    capitalize = True
    for _ in range(count):
        if numbers and rng.random() < 0.12:
            w = str(rng.choice([rng.randint(0, 99), rng.randint(100, 9999), rng.randint(1900, 2030)]))
        else:
            w = rng.choices(pool, weights=word_weights)[0]
            if out and w == out[-1].strip('".,;:?!()') and len(pool) > 1:
                w = rng.choices(pool, weights=word_weights)[0]  # avoid "the the"
        if punctuation:
            if capitalize:
                w = w[:1].upper() + w[1:]
                capitalize = False
            r = rng.random()
            if r < 0.10:
                w += rng.choice(PUNCT_END)
                capitalize = True
            elif r < 0.18:
                w += rng.choice(PUNCT_MID)
            elif r < 0.21:
                w = f'"{w}"'
            elif r < 0.23:
                w = f"({w})"
        out.append(w)
    if punctuation and out and out[-1][-1] not in ".?!":
        out[-1] += "."
    return " ".join(out)


def code_snippet(rng: Optional[random.Random] = None) -> str:
    return (rng or random.Random()).choice(CODE_SNIPPETS)
