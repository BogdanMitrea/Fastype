"""Practice screen: mode chips, live stats, the typing area, the keyboard and results."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QInputDialog, QMenu, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import texts
from ..settings import settings
from ..engine import BACKSPACE, SessionResult, TypingSession
from ..store import Store, weakness_scores
from . import theme as t
from .charts import AreaChart
from .keyboard import KeyboardWidget
from .sound import AUDIO_FILTER, Sounds, import_sound
from .typing_view import TypingView
from .widgets import Chip, ChipRow, Divider, StatCard, Toggle, Tween, hint_text

MODES = ["Words", "Timed", "Weak keys", "Code", "Custom"]
WORD_COUNTS = ["10", "25", "50", "100"]
DURATIONS = ["15s", "30s", "60s", "120s"]


def fade_in(w: QWidget, ms: int = 260) -> None:
    effect = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", w)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    # Drop the effect afterwards: it would otherwise re-render the widget offscreen forever.
    anim.finished.connect(lambda: w.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeleteWhenStopped)


class Hints(QWidget):
    def __init__(self, parts: list[tuple[str, str]], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.parts = parts
        self.setFixedHeight(30)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        hint_text(p, QRectF(self.rect()), self.parts)


class LiveStats(QWidget):
    """WPM, accuracy, time and streak above the text, updating as you type."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.wpm = Tween(self.update, 350)
        self.acc = Tween(self.update, 350, 100)
        self.pulse = Tween(self.update, 700, 0.0, QEasingCurve.OutQuad)
        self.clock = "0"
        self.clock_caption = "time"
        self.streak = 0
        self.started = False
        self.message = ""
        self.setFixedHeight(70)

    def set_streak(self, n: int) -> None:
        if n and n % 25 == 0 and n != self.streak:
            self.pulse.to(0.0, 1.0)  # flare up every 25 correct keys in a row
        self.streak = n

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.started:
            p.setPen(t.MUTED)
            p.setFont(t.ui(15, QFont.Medium))
            p.drawText(QRectF(self.rect()).adjusted(8, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, self.message)
            return
        cols = [("wpm", f"{self.wpm.value:.0f}" if self.wpm.value >= 0 else "–", True),
                ("accuracy", f"{self.acc.value:.0f}%", False),
                (self.clock_caption, self.clock, False)]
        x = 8.0
        for caption, value, accent in cols:
            p.setPen(t.MUTED)
            p.setFont(t.ui(10, QFont.DemiBold, spacing=1.4))
            p.drawText(QRectF(x, 4, 200, 16), Qt.AlignLeft, caption.upper())
            box = QRectF(x, 20, 220, 46)
            p.setPen(t.ACCENT if accent else t.TEXT)
            p.setFont(t.mono(28, QFont.Medium))
            p.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, value)
            w = p.fontMetrics().horizontalAdvance(value)
            x += max(w, 70) + 44

        # Streak on the right
        if self.streak >= 5:
            right = QRectF(self.width() - 220, 0, 212, self.height())
            p.setPen(t.MUTED)
            p.setFont(t.ui(10, QFont.DemiBold, spacing=1.4))
            p.drawText(right.adjusted(0, 4, 0, 0), Qt.AlignRight | Qt.AlignTop, "STREAK")
            p.setFont(t.mono(28, QFont.Medium))
            p.setPen(t.mix(t.TEXT, t.ACCENT, self.pulse.value))  # flashes orange every 25
            p.drawText(right.adjusted(0, 20, 0, -4), Qt.AlignRight | Qt.AlignVCenter, f"{self.streak}")


class BigNumber(QWidget):
    """The giant WPM figure on the results screen, counting up."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.value = Tween(self.update, 1100, 0.0, QEasingCurve.OutExpo)
        self.best = False
        self.setMinimumSize(260, 200)

    def show_value(self, v: float, best: bool) -> None:
        self.best = best
        self.value.to(v, 0.0)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(t.MUTED)
        p.setFont(t.ui(11, QFont.DemiBold, spacing=2))
        p.drawText(r.adjusted(0, 10, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "WORDS PER MINUTE")
        p.setPen(t.TEXT)
        p.setFont(t.mono(92, QFont.Medium))
        p.drawText(r.adjusted(0, 0, 0, -10), Qt.AlignCenter, f"{self.value.value:.0f}")
        if self.best:
            p.setFont(t.ui(11, QFont.Bold, spacing=1.5))
            bw = p.fontMetrics().horizontalAdvance("NEW PERSONAL BEST") + 36
            badge = QRectF(r.center().x() - bw / 2, r.bottom() - 36, bw, 28)
            p.setPen(Qt.NoPen)
            p.setBrush(t.ACCENT)
            p.drawRoundedRect(badge, 14, 14)
            p.setPen(t.SURFACE)
            p.setFont(t.ui(11, QFont.Bold, spacing=1.5))
            p.drawText(badge, Qt.AlignCenter, "NEW PERSONAL BEST")


class MissedKeys(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.keys: list[tuple[str, int]] = []
        self.setFixedHeight(56)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(t.MUTED)
        p.setFont(t.ui(10, QFont.DemiBold, spacing=1.4))
        p.drawText(QRectF(0, 0, 200, 16), Qt.AlignLeft, "MISSED KEYS")
        if not self.keys:
            p.setPen(t.GOOD)
            p.setFont(t.ui(14, QFont.DemiBold))
            p.drawText(QRectF(0, 20, 400, 36), Qt.AlignLeft | Qt.AlignVCenter, "None. A flawless run!")
            return
        x = 0.0
        for k, n in self.keys:
            label = {" ": "space", "\n": "return"}.get(k, k)
            cap = t.keycap(p, QRectF(x, 20, max(36, 16 + 9 * len(label)), 34), 7,
                           t.mix(t.KEY, t.BAD, 0.12), t.mix(t.KEY_EDGE, t.BAD, 0.35), 3)
            p.setPen(t.BAD)
            p.setFont(t.mono(14, QFont.Medium))
            p.drawText(cap, Qt.AlignCenter, label)
            p.setPen(t.MUTED)
            p.setFont(t.ui(12, QFont.Medium))
            p.drawText(QRectF(cap.right() + 6, 20, 40, 34), Qt.AlignLeft | Qt.AlignVCenter, f"×{n}")
            x = cap.right() + 46


class ResultsPanel(QWidget):
    """Shown after a run. Enter/Tab = next text, Esc = retry the same one."""

    def __init__(self, on_next, on_retry, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.on_next, self.on_retry = on_next, on_retry
        self.setFocusPolicy(Qt.StrongFocus)
        self.big = BigNumber()
        self.cards = {
            "accuracy": StatCard("Accuracy", "{:.1f}", "%"),
            "raw": StatCard("Raw speed", suffix="wpm"),
            "consistency": StatCard("Consistency", suffix="%"),
            "time": StatCard("Time", "{:.1f}", "s"),
            "keys": StatCard("Keys typed"),
            "errors": StatCard("Errors"),
        }
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, i // 3, i % 3)
        self.missed = MissedKeys()
        right = QVBoxLayout()
        right.addStretch(1)
        right.addLayout(grid)
        right.addSpacing(16)
        right.addWidget(self.missed)
        right.addStretch(1)
        top = QHBoxLayout()
        top.addWidget(self.big, 2)
        top.addSpacing(24)
        top.addLayout(right, 3)
        self.chart = AreaChart(min_height=150)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top, 3)
        lay.addSpacing(8)
        lay.addWidget(self.chart, 2)
        lay.addWidget(Hints([("return", "next text"), ("esc", "try this text again")]))

    def show_result(self, r: SessionResult, best_before: float) -> None:
        self.big.show_value(r.wpm, bool(best_before) and r.wpm > best_before)
        values = {"accuracy": r.accuracy, "raw": r.raw_wpm, "consistency": r.consistency,
                  "time": r.duration, "keys": r.chars_typed, "errors": r.errors}
        for k, v in values.items():
            self.cards[k].set_value(v)
        self.cards["accuracy"].highlight = r.accuracy >= 98
        self.missed.keys = r.problem_keys(6)
        self.missed.update()
        self.chart.set_values(r.wpm_timeline, "speed through the run, second by second (wpm)")

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            self.on_next()
        elif e.key() == Qt.Key_Escape:
            self.on_retry()
        else:
            super().keyPressEvent(e)

    def focusNextPrevChild(self, next: bool) -> bool:
        return False


class PracticePage(QWidget):
    def __init__(self, store: Store, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self.session: Optional[TypingSession] = None
        self.custom_text = "The quick brown fox jumps over the lazy dog."
        self.saved = False

        # Controls
        self.mode = ChipRow(MODES)
        self.length = ChipRow()
        self.settings = settings()
        self.language = ChipRow(list(texts.LANGUAGES), self.settings.value("language", "English"))
        self.tier = ChipRow(list(texts.TIERS), self.settings.value("tier", "top 1k"))
        self.tier.setToolTip("How far down the list of common words to go")
        self.punct = Toggle("@ punctuation")
        self.numbers = Toggle("# numbers")
        self.edit = Chip("✎ edit text")
        self.edit.setCheckable(False)
        self.show_kb = Toggle("⌨ keyboard")
        self.show_kb.setChecked(self.settings.value("keyboard", True, bool))
        self.show_kb._on.set(1.0 if self.show_kb.isChecked() else 0.0)
        self.sound_on = Toggle("♪ sound")
        self.sound_on.setChecked(self.settings.value("sound", True, bool))
        self.sound_on._on.set(1.0 if self.sound_on.isChecked() else 0.0)
        self.sounds = Sounds(self.sound_on.isChecked())
        saved_miss = self.settings.value("miss_sound", "")
        self.sounds.let_finish = self.settings.value("miss_let_finish", True, bool)
        self.sounds.set_miss_sound(Path(saved_miss) if saved_miss else None,
                                   self.settings.value("miss_volume", 80, int) / 100)
        self.miss = Chip("")
        self.miss.setCheckable(False)
        self.miss.setToolTip("Sound for a missed key")
        self.miss.clicked.connect(self._miss_menu)
        self._update_miss_chip()
        self._dividers = [Divider() for _ in range(4)]
        modes = QHBoxLayout()
        modes.addStretch(1)
        modes.addWidget(self.mode)
        modes.addWidget(self._dividers[3])
        modes.addWidget(self.show_kb)
        modes.addWidget(self.sound_on)
        modes.addWidget(self.miss)
        modes.addStretch(1)
        options = QHBoxLayout()
        options.setSpacing(6)
        options.addStretch(1)
        for w in (self.length, self._dividers[0], self.language, self._dividers[1], self.tier,
                  self._dividers[2], self.punct, self.numbers, self.edit):
            options.addWidget(w)
        options.addStretch(1)
        bar = QVBoxLayout()
        bar.setSpacing(8)
        bar.addLayout(modes)
        bar.addLayout(options)

        self.live = LiveStats()
        self.view = TypingView()
        self.view.typed.connect(self._on_typed)
        self.view.keystroke.connect(self._on_keystroke)
        self.view.restart.connect(self.new_run)
        self.keyboard = KeyboardWidget()
        self.keyboard.setVisible(self.show_kb.isChecked())

        typing = QWidget()
        tl = QVBoxLayout(typing)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addStretch(1)
        tl.addWidget(self.live)
        tl.addSpacing(6)
        tl.addWidget(self.view)
        tl.addStretch(1)
        tl.addWidget(self.keyboard, 3)
        tl.addWidget(Hints([("tab", "new text"), ("esc", "restart"), ("⌥ delete", "delete word")]))

        self.results = ResultsPanel(lambda: self.new_run(True), lambda: self.new_run(False))
        self.stack = QStackedWidget()
        self.stack.addWidget(typing)
        self.stack.addWidget(self.results)
        self.typing_page = typing

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 8, 36, 14)
        lay.addLayout(bar)
        lay.addSpacing(10)
        lay.addWidget(self.stack, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self.mode.changed.connect(self._mode_changed)
        self.length.changed.connect(lambda _: self.new_run(True))
        self.language.changed.connect(lambda v: self._remember("language", v))
        self.tier.changed.connect(lambda v: self._remember("tier", v))
        self.punct.toggled.connect(lambda _: self.new_run(True))
        self.numbers.toggled.connect(lambda _: self.new_run(True))
        self.show_kb.toggled.connect(self._toggle_keyboard)
        self.sound_on.toggled.connect(self._toggle_sound)
        self.edit.clicked.connect(self._ask_custom)
        self._mode_changed()

    def _remember(self, key: str, value: str) -> None:
        self.settings.setValue(key, value)
        self.new_run(True)

    def _toggle_keyboard(self, on: bool) -> None:
        self.keyboard.setVisible(on)
        self.settings.setValue("keyboard", on)
        self.view.setFocus()

    def _update_miss_chip(self) -> None:
        path = self.sounds.miss_path
        name = path.stem if path else "built-in"
        self.miss.setText(f"✕ miss: {name if len(name) <= 14 else name[:13] + '…'}  ▾")
        self.miss.updateGeometry()
        self.miss.update()

    def _miss_menu(self) -> None:
        menu = QMenu(self)
        current = self.sounds.miss_path
        builtin = menu.addAction("Built-in tone")
        builtin.setCheckable(True)
        builtin.setChecked(current is None)
        builtin.triggered.connect(lambda: self._set_miss(None))
        saved = self.settings.value("miss_sound_last", "")
        if saved and Path(saved).exists():
            custom = menu.addAction(Path(saved).name)
            custom.setCheckable(True)
            custom.setChecked(current is not None and str(current) == saved)
            custom.triggered.connect(lambda: self._set_miss(Path(saved)))
        menu.addAction("Choose sound file…", self._choose_miss)
        menu.addSeparator()
        menu.addAction("▶  Play it", lambda: self.sounds.play_miss(force=True))
        volume = menu.addMenu("Volume")
        now = self.settings.value("miss_volume", 80, int)
        for pct in (25, 50, 80, 100):
            a = volume.addAction(f"{pct}%")
            a.setCheckable(True)
            a.setChecked(pct == now)
            a.triggered.connect(lambda _=False, v=pct: self._set_miss_volume(v))
        finish = menu.addAction("Let it finish before playing again")
        finish.setCheckable(True)
        finish.setChecked(self.sounds.let_finish)
        finish.toggled.connect(self._set_let_finish)
        menu.exec(self.miss.mapToGlobal(self.miss.rect().bottomLeft()))
        self.view.setFocus()

    def _choose_miss(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Sound for a missed key", str(Path.home()), AUDIO_FILTER)
        if path:
            self._set_miss(import_sound(path))
            self.sounds.play_miss(force=True)

    def _set_miss(self, path: Optional[Path]) -> None:
        self.sounds.set_miss_sound(path, self.settings.value("miss_volume", 80, int) / 100)
        self.settings.setValue("miss_sound", str(path) if path else "")
        if path:
            self.settings.setValue("miss_sound_last", str(path))
        self._update_miss_chip()

    def _set_miss_volume(self, pct: int) -> None:
        self.settings.setValue("miss_volume", pct)
        self.sounds.set_miss_volume(pct / 100)
        self.sounds.play_miss(force=True)

    def _set_let_finish(self, on: bool) -> None:
        self.sounds.let_finish = on
        self.settings.setValue("miss_let_finish", on)

    def _toggle_sound(self, on: bool) -> None:
        self.sounds.enabled = on
        self.settings.setValue("sound", on)
        self.view.setFocus()

    # --- runs ----------------------------------------------------------------
    def _mode_changed(self, *_args) -> None:
        mode = self.mode.current()
        if mode == "Timed":
            self.length.set_items(DURATIONS, "30s")
        elif mode in ("Words", "Weak keys"):
            self.length.set_items(WORD_COUNTS, "25")
        words_like = mode in ("Words", "Timed", "Weak keys")
        for w in (self.length, self.language, self.tier, self.punct, self.numbers, *self._dividers[:3]):
            w.setVisible(words_like)
        self.edit.setVisible(mode == "Custom")
        self.new_run(True)

    def _ask_custom(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Custom text", "Paste the text to practise:",
                                                 self.custom_text)
        if ok and text.strip():
            self.custom_text = text.strip()
            self.new_run(True)
        self.view.setFocus()

    def new_run(self, new_text: bool = True) -> None:
        mode = self.mode.current()
        if new_text or self.session is None:
            target, limit, lines, info = self._make_text(mode)
        else:
            target, limit = self.session.target, self.session.time_limit
            lines, info = self.view.wanted_lines, self.live.message
        self.session = TypingSession(target, time_limit=limit, auto_indent=(mode == "Code"))
        self.saved = False
        self.live.message = info
        self.live.started = False
        self.live.wpm.set(0)
        self.live.acc.set(100)
        self.live.set_streak(0)
        self.view.set_session(self.session, lines)
        self.keyboard.set_next(self.view.next_char())
        if self.stack.currentWidget() is not self.typing_page:
            self.stack.setCurrentWidget(self.typing_page)
            fade_in(self.typing_page)
        self.view.setFocus()
        self._update_live()

    def _make_text(self, mode: str):
        lang, tier = self.language.current(), self.tier.current()
        p, n = self.punct.isChecked(), self.numbers.isChecked()
        if mode == "Timed":
            seconds = int(self.length.current().rstrip("s"))
            return (texts.words(seconds * 4, lang, p, n, tier=tier), float(seconds), 3,
                    f"{seconds} seconds on the clock. It starts with your first key.")
        if mode == "Code":
            target = texts.code_snippet()
            return (target, None, min(5, target.count("\n") + 1),
                    "Return for new lines. Indentation is typed for you.")
        if mode == "Custom":
            return self.custom_text, None, 4, "Your own text. Edit it with ✎ above."
        count = int(self.length.current())
        weights = None
        info = "Start typing when you're ready."
        if mode == "Weak keys":
            weights = weakness_scores(self.store.key_stats())
            if weights:
                top = sorted(weights, key=lambda c: -weights[c])[:5]
                info = "Drilling your weakest keys:  " + "  ".join(c.upper() for c in top)
            else:
                info = "Not enough history yet. Finish a few runs and this mode adapts to you."
        return texts.words(count, lang, p, n, weights=weights, tier=tier), None, 3, info

    # --- live updates ----------------------------------------------------------
    def _on_keystroke(self, ch: str, correct: bool) -> None:
        self.keyboard.flash(ch, correct)
        self.sounds.keystroke(ch, correct)

    def _on_typed(self) -> None:
        self.keyboard.set_next(self.view.next_char())
        self._update_live()
        if self.session and self.session.finished:
            self._finish()

    def _tick(self) -> None:
        if not self.session or self.stack.currentWidget() is not self.typing_page:
            return
        self.view.tick()
        if self.session.check_time():
            self._finish()
        elif self.session.started:
            self._update_live()

    def _update_live(self) -> None:
        s = self.session
        if not s:
            return
        self.live.started = s.started
        if s.started:
            r = s.result()
            self.live.wpm.to(r.wpm if s.elapsed() >= 1 else -1)  # the first second is too noisy
            self.live.acc.to(r.accuracy)
            if s.time_limit:
                self.live.clock_caption, self.live.clock = "time left", f"{s.time_left():.0f}s"
            else:
                self.live.clock_caption = "progress"
                self.live.clock = f"{s.position}/{len(s.target)}"
            streak = 0
            for k in reversed(s.keystrokes):
                if k.typed == BACKSPACE:
                    continue
                if not k.correct:
                    break
                streak += 1
            self.live.set_streak(streak)
        self.live.update()

    def _finish(self) -> None:
        if self.saved or not self.session:
            return
        self.saved = True
        r = self.session.result()
        if r.chars_typed == 0:
            self.new_run(False)
            return
        best_before = self.store.summary()["best_wpm"]
        self.store.save(self.mode.current(), r)
        self.results.show_result(r, best_before)
        self.sounds.play("done")
        self.stack.setCurrentWidget(self.results)
        fade_in(self.results)
        self.results.setFocus()
