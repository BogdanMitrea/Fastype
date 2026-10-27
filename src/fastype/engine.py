"""Typing session logic, independent of any UI.

A session holds a target text and what has been typed so far. Every key press is
recorded with a timestamp so results and per-key statistics can be computed later.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

BACKSPACE = "\b"


@dataclass
class Keystroke:
    t: float                 # seconds since the session started
    typed: str               # the character typed, or BACKSPACE
    expected: Optional[str]  # the character that was due, None for backspace
    correct: bool


@dataclass
class KeyStat:
    hits: int = 0
    misses: int = 0
    latency_total: float = 0.0  # seconds, summed over correct hits
    latency_count: int = 0


@dataclass
class SessionResult:
    wpm: float
    raw_wpm: float
    accuracy: float          # percent of keystrokes that were correct
    consistency: float       # percent, 100 = perfectly even rhythm
    duration: float          # seconds
    chars_typed: int
    errors: int
    key_stats: dict[str, KeyStat] = field(default_factory=dict)
    wpm_timeline: list[float] = field(default_factory=list)  # one value per second

    def problem_keys(self, n: int = 5) -> list[tuple[str, int]]:
        """Keys with the most misses in this session."""
        missed = [(k, s.misses) for k, s in self.key_stats.items() if s.misses]
        return sorted(missed, key=lambda kv: -kv[1])[:n]


class TypingSession:
    def __init__(
        self,
        target: str,
        time_limit: Optional[float] = None,
        auto_indent: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.target = target
        self.time_limit = time_limit
        self.auto_indent = auto_indent
        self._clock = clock
        self._start: Optional[float] = None
        self._end: Optional[float] = None
        # Each typed entry is (char, auto); auto chars were filled in for the user
        # (indentation after a newline) and are not counted as keystrokes.
        self.typed: list[tuple[str, bool]] = []
        self.keystrokes: list[Keystroke] = []

    # --- state -------------------------------------------------------------
    @property
    def started(self) -> bool:
        return self._start is not None

    @property
    def finished(self) -> bool:
        return self._end is not None

    @property
    def position(self) -> int:
        return len(self.typed)

    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        end = self._end if self._end is not None else self._clock()
        elapsed = end - self._start
        if self.time_limit is not None:
            elapsed = min(elapsed, self.time_limit)
        return elapsed

    def time_left(self) -> Optional[float]:
        if self.time_limit is None:
            return None
        return max(0.0, self.time_limit - self.elapsed())

    def is_correct_at(self, i: int) -> bool:
        return self.typed[i][0] == self.target[i]

    # --- input -------------------------------------------------------------
    def type_char(self, ch: str) -> None:
        if self.finished or self.position >= len(self.target):
            return
        now = self._now()
        if self.check_time():
            return
        expected = self.target[self.position]
        correct = ch == expected
        self.keystrokes.append(Keystroke(now, ch, expected, correct))
        self.typed.append((ch, False))
        if correct and ch == "\n" and self.auto_indent:
            while self.position < len(self.target) and self.target[self.position] == " ":
                self.typed.append((" ", True))
        if self.position >= len(self.target):
            self._end = self._clock()

    def backspace(self, word: bool = False) -> None:
        """Delete one character, or back to the start of the word with word=True."""
        if self.finished or not self.typed:
            return
        self.keystrokes.append(Keystroke(self._now(), BACKSPACE, None, True))
        self._pop_one()
        if word:
            while self.typed and not self.typed[-1][0].isspace():
                self._pop_one()

    def _pop_one(self) -> None:
        while self.typed and self.typed[-1][1]:  # take auto indentation with it
            self.typed.pop()
        if self.typed:
            self.typed.pop()

    def check_time(self) -> bool:
        """End the session if its time limit has passed. Returns True if finished."""
        if self.finished:
            return True
        if self.time_limit is not None and self.started:
            if self._clock() - self._start >= self.time_limit:
                self._end = self._start + self.time_limit
                return True
        return False

    def _now(self) -> float:
        if self._start is None:
            self._start = self._clock()
        return self._clock() - self._start

    # --- results -----------------------------------------------------------
    def result(self) -> SessionResult:
        duration = max(self.elapsed(), 1e-6)
        minutes = duration / 60
        typed_keys = [k for k in self.keystrokes if k.typed != BACKSPACE]
        correct_chars = sum(
            1 for i, (_, auto) in enumerate(self.typed) if not auto and self.is_correct_at(i)
        )
        wpm = correct_chars / 5 / minutes
        raw_wpm = len(typed_keys) / 5 / minutes
        errors = sum(1 for k in typed_keys if not k.correct)
        accuracy = 100.0 * (len(typed_keys) - errors) / len(typed_keys) if typed_keys else 0.0
        return SessionResult(
            wpm=wpm,
            raw_wpm=raw_wpm,
            accuracy=accuracy,
            consistency=self._consistency(typed_keys),
            duration=duration,
            chars_typed=len(typed_keys),
            errors=errors,
            key_stats=self._key_stats(),
            wpm_timeline=self._timeline(typed_keys, duration),
        )

    def _key_stats(self) -> dict[str, KeyStat]:
        stats: dict[str, KeyStat] = {}
        prev_t: Optional[float] = None
        for k in self.keystrokes:
            if k.typed != BACKSPACE and k.expected is not None:
                s = stats.setdefault(k.expected, KeyStat())
                if k.correct:
                    s.hits += 1
                    # Latency only makes sense between two consecutive presses.
                    if prev_t is not None and k.t - prev_t < 2.0:
                        s.latency_total += k.t - prev_t
                        s.latency_count += 1
                else:
                    s.misses += 1
            prev_t = k.t
        return stats

    @staticmethod
    def _consistency(typed_keys: list[Keystroke]) -> float:
        gaps = [b.t - a.t for a, b in zip(typed_keys, typed_keys[1:]) if b.t - a.t < 2.0]
        if len(gaps) < 2:
            return 100.0
        mean = statistics.fmean(gaps)
        if mean <= 0:
            return 100.0
        cv = statistics.pstdev(gaps) / mean
        return max(0.0, 100.0 * (1 - cv))

    @staticmethod
    def _timeline(typed_keys: list[Keystroke], duration: float) -> list[float]:
        seconds = max(1, int(duration + 0.999))
        counts = [0] * seconds
        for k in typed_keys:
            counts[min(int(k.t), seconds - 1)] += 1
        wpm = [c / 5 * 60 for c in counts]  # chars per second -> words per minute
        # The last second is usually partial: scale it up, or drop it if too short to mean much.
        tail = duration - (seconds - 1)
        if tail < 0.5 and seconds > 1:
            wpm.pop()
        elif tail < 1:
            wpm[-1] /= tail
        return wpm
