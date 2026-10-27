"""SQLite storage for session history and lifetime per-key statistics."""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .engine import KeyStat, SessionResult


def default_db_path() -> Path:
    if env := os.environ.get("FASTYPE_DB"):
        return Path(env)
    return Path.home() / "Library" / "Application Support" / "Fastype" / "fastype.db"


@dataclass
class SessionRow:
    started_at: float
    mode: str
    wpm: float
    raw_wpm: float
    accuracy: float
    consistency: float
    duration: float


class Store:
    def __init__(self, path: Path | str | None = None):
        path = Path(path) if path else default_db_path()
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY,
                started_at REAL NOT NULL,
                mode TEXT NOT NULL,
                wpm REAL, raw_wpm REAL, accuracy REAL, consistency REAL,
                duration REAL, chars INTEGER, errors INTEGER
            );
            CREATE TABLE IF NOT EXISTS key_stats (
                ch TEXT PRIMARY KEY,
                hits INTEGER NOT NULL DEFAULT 0,
                misses INTEGER NOT NULL DEFAULT 0,
                latency_total REAL NOT NULL DEFAULT 0,
                latency_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )

    def save(self, mode: str, r: SessionResult) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO sessions (started_at, mode, wpm, raw_wpm, accuracy, consistency,"
                " duration, chars, errors) VALUES (?,?,?,?,?,?,?,?,?)",
                (time.time(), mode, r.wpm, r.raw_wpm, r.accuracy, r.consistency,
                 r.duration, r.chars_typed, r.errors),
            )
            for ch, s in r.key_stats.items():
                self.db.execute(
                    "INSERT INTO key_stats (ch, hits, misses, latency_total, latency_count)"
                    " VALUES (?,?,?,?,?) ON CONFLICT(ch) DO UPDATE SET"
                    " hits = hits + excluded.hits, misses = misses + excluded.misses,"
                    " latency_total = latency_total + excluded.latency_total,"
                    " latency_count = latency_count + excluded.latency_count",
                    (ch, s.hits, s.misses, s.latency_total, s.latency_count),
                )

    def sessions(self, limit: int = 100) -> list[SessionRow]:
        rows = self.db.execute(
            "SELECT started_at, mode, wpm, raw_wpm, accuracy, consistency, duration"
            " FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [SessionRow(*r) for r in reversed(rows)]

    def key_stats(self) -> dict[str, KeyStat]:
        rows = self.db.execute(
            "SELECT ch, hits, misses, latency_total, latency_count FROM key_stats"
        ).fetchall()
        return {ch: KeyStat(h, m, lt, lc) for ch, h, m, lt, lc in rows}

    def summary(self) -> dict[str, float]:
        n, best, avg, acc, secs = self.db.execute(
            "SELECT COUNT(*), MAX(wpm), AVG(wpm), AVG(accuracy), SUM(duration) FROM sessions"
        ).fetchone()
        return {"sessions": n or 0, "best_wpm": best or 0.0, "avg_wpm": avg or 0.0,
                "avg_accuracy": acc or 0.0, "total_seconds": secs or 0.0}

    def reset(self) -> None:
        with self.db:
            self.db.execute("DELETE FROM sessions")
            self.db.execute("DELETE FROM key_stats")


def weakness_scores(stats: dict[str, KeyStat], min_samples: int = 8) -> dict[str, float]:
    """Score each letter by how much it needs practice (0 = fine, higher = weaker).

    Combines error rate with how much slower than average the key is.
    """
    letters = {c.lower(): s for c, s in stats.items() if c.isalpha()}
    sampled = {c: s for c, s in letters.items() if s.hits + s.misses >= min_samples}
    if not sampled:
        return {}
    latencies = {c: s.latency_total / s.latency_count for c, s in sampled.items() if s.latency_count}
    mean_latency = sum(latencies.values()) / len(latencies) if latencies else 0.0
    scores = {}
    for c, s in sampled.items():
        error_rate = s.misses / (s.hits + s.misses)
        slowness = 0.0
        if mean_latency and c in latencies:
            slowness = max(0.0, latencies[c] / mean_latency - 1.0)
        scores[c] = 20 * error_rate + 3 * slowness
    return scores
