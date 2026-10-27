"""Key sounds, synthesised in code the first time the app runs.

Each sound is a short WAV written to the cache folder and played with QSoundEffect.
Keys have a few slightly different variants so fast typing doesn't sound mechanical.

The sound for a missed key can be replaced by any audio file the user picks (MP3, WAV,
M4A, …). It is copied into the app's own folder and played with QMediaPlayer.
"""
from __future__ import annotations

import itertools
import math
import random
import shutil
import struct
import wave
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect

AUDIO_FILTER = "Audio (*.mp3 *.wav *.m4a *.aac *.aiff *.aif *.caf *.ogg *.flac)"


def import_sound(path: str | Path) -> Path:
    """Copy a chosen sound into the app's folder, so it keeps working if the original moves."""
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "sounds"
    folder.mkdir(parents=True, exist_ok=True)
    src = Path(path)
    dest = folder / src.name
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    return dest

RATE = 44100
VERSION = "v1"  # bump to regenerate the files after changing the synthesis


def _key(pitch: float, seed: int, length: float = 0.07, body: float = 0.5) -> list[float]:
    """A soft keyboard 'thock': a filtered noise click over a short low tone."""
    rng = random.Random(seed)
    out, lp = [], 0.0
    for i in range(int(length * RATE)):
        t = i / RATE
        lp += 0.3 * (rng.uniform(-1, 1) - lp)  # low-passed noise
        s = (0.6 * lp * math.exp(-t / 0.002)
             + body * math.sin(2 * math.pi * pitch * t) * math.exp(-t / 0.014)
             + 0.12 * math.sin(2 * math.pi * 2900 * t) * math.exp(-t / 0.0009))
        out.append(s)
    return out


def _tone(notes: list[tuple[float, float, float]], length: float, decay: float) -> list[float]:
    """Sine notes as (frequency, start, level) with a soft attack and exponential decay."""
    out = [0.0] * int(length * RATE)
    for freq, start, level in notes:
        first = int(start * RATE)
        for i in range(first, len(out)):
            t = (i - first) / RATE
            env = min(1.0, t / 0.004) * math.exp(-t / decay)
            out[i] += level * env * (math.sin(2 * math.pi * freq * t)
                                     + 0.25 * math.sin(4 * math.pi * freq * t))
    return out


def _sounds() -> dict[str, list[float]]:
    return {
        "key0": _key(230, 1), "key1": _key(250, 2), "key2": _key(215, 3), "key3": _key(240, 4),
        "space": _key(160, 5, 0.09, 0.65),
        "back": _key(200, 6, 0.06, 0.35),
        "error": _tone([(196, 0, 0.5), (165, 0.05, 0.5)], 0.2, 0.04),
        "done": _tone([(659.3, 0, 0.35), (880, 0.09, 0.35), (1318.5, 0.18, 0.18)], 0.9, 0.18),
    }


def _write(path: Path, samples: list[float], peak: float = 0.7) -> None:
    top = max(abs(s) for s in samples) or 1.0
    fade = int(0.003 * RATE)  # avoid a click at the very end
    frames = bytearray()
    for i, s in enumerate(samples):
        if i >= len(samples) - fade:
            s *= (len(samples) - i) / fade
        frames += struct.pack("<h", int(s / top * peak * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


class Sounds:
    VOICES = 4  # copies of each sound, so quick repeats don't cut each other off

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        folder = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)) / f"sounds-{VERSION}"
        folder.mkdir(parents=True, exist_ok=True)
        self._effects: dict[str, itertools.cycle] = {}
        for name, samples in _sounds().items() if not (folder / "done.wav").exists() else []:
            _write(folder / f"{name}.wav", samples)
        for name in ("key0", "key1", "key2", "key3", "space", "back", "error", "done"):
            voices = []
            for _ in range(self.VOICES):
                e = QSoundEffect()
                e.setSource(QUrl.fromLocalFile(str(folder / f"{name}.wav")))
                e.setVolume(0.45 if name != "done" else 0.35)
                voices.append(e)
            self._effects[name] = itertools.cycle(voices)
        self._rng = random.Random()
        self._miss_audio = QAudioOutput()
        self._miss_player = QMediaPlayer()
        self._miss_player.setAudioOutput(self._miss_audio)
        self.miss_path: Optional[Path] = None
        self.let_finish = True  # a long custom sound isn't restarted by every miss

    def set_miss_sound(self, path: Optional[Path], volume: float = 0.8) -> None:
        """Use a custom file for missed keys, or None for the built-in tone."""
        self.miss_path = path if path and path.exists() else None
        self._miss_player.stop()
        self._miss_player.setSource(QUrl.fromLocalFile(str(self.miss_path)) if self.miss_path else QUrl())
        self._miss_audio.setVolume(volume)

    def set_miss_volume(self, volume: float) -> None:
        self._miss_audio.setVolume(volume)

    def play_miss(self, force: bool = False) -> None:
        if not (self.enabled or force):
            return
        if not self.miss_path:
            next(self._effects["error"]).play()
            return
        playing = self._miss_player.playbackState() == QMediaPlayer.PlayingState
        if playing and self.let_finish and not force:
            return
        self._miss_player.setPosition(0)
        self._miss_player.play()

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        if name == "key":
            name = f"key{self._rng.randrange(4)}"
        next(self._effects[name]).play()

    def keystroke(self, ch: str, correct: bool) -> None:
        if ch == "backspace":
            self.play("back")
        elif not correct:
            self.play_miss()
        else:
            self.play("space" if ch in " \n" else "key")
