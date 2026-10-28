"""The widget the user types into: draws the target text, coloured by progress."""
from __future__ import annotations

import math
import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetricsF, QInputMethodEvent, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..engine import TypingSession
from . import theme as t
from .widgets import Tween


def wrap(text: str, cols: int) -> list[tuple[int, int]]:
    """Split text into display lines as (start, end) index ranges.

    Newlines force a break; otherwise lines break after the last space that fits.
    """
    cols = max(cols, 8)
    lines: list[tuple[int, int]] = []
    start, last_space = 0, -1
    for i, ch in enumerate(text):
        if ch == "\n":
            lines.append((start, i + 1))
            start, last_space = i + 1, -1
            continue
        if ch == " ":
            last_space = i
        if i - start + 1 > cols and ch != " ":
            brk = last_space + 1 if last_space >= start else i
            lines.append((start, brk))
            start, last_space = brk, -1
    if start < len(text) or not lines:
        lines.append((start, len(text)))
    return lines


class TypingView(QWidget):
    typed = Signal()
    keystroke = Signal(str, bool)  # character (or "backspace"), correct
    restart = Signal(bool)         # True = new text, False = same text again

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session: Optional[TypingSession] = None
        self.visible_lines = self.wanted_lines = 3
        self.setFocusPolicy(Qt.StrongFocus)
        # Needed for dead keys (Option+U, U -> ü) to arrive as committed text.
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.font_ = t.mono(25)
        self.metrics = QFontMetricsF(self.font_)
        self.char_w = self.metrics.horizontalAdvance("M")
        self.line_h = self.metrics.height() * 1.6
        self.margin_x = 8.0
        self.top = 18.0  # room for the progress line
        self._caret_x = Tween(self.update, 90)
        self._caret_y = Tween(self.update, 90)
        self._scroll = Tween(self.update, 260)
        self._progress = Tween(self.update, 200)
        self._last_input = 0.0
        self._cols = 0
        self._lines: list[tuple[int, int]] = []
        self._blink = QTimer(self)
        self._blink.setInterval(33)
        self._blink.timeout.connect(self.update)
        self._blink.start()

    def set_session(self, session: TypingSession, visible_lines: int = 3) -> None:
        self.session = session
        self.wanted_lines = visible_lines
        self.setMinimumHeight(self._height_for(min(3, visible_lines)))
        self.setMaximumHeight(self._height_for(visible_lines))
        self._fit_lines()
        self._relayout()
        first = self._first_line()
        self._scroll.set(first)
        x, y = self._caret_pos(first)
        self._caret_x.set(x)
        self._caret_y.set(y)
        self._progress.set(0)
        self.updateGeometry()
        self.update()

    def _height_for(self, lines: int) -> int:
        # Round up: rounding down left the last line a fraction of a pixel short of fitting.
        return math.ceil(self.top + self.line_h * lines + 12)

    def _fit_lines(self) -> None:
        """Show as many of the wanted lines as the widget has room for (when the window is small)."""
        fit = int((self.height() - self.top - 12 + 0.5) // self.line_h)
        self.visible_lines = max(1, min(self.wanted_lines, fit)) if fit > 0 else self.wanted_lines

    def sizeHint(self) -> QSize:
        return QSize(600, self._height_for(self.wanted_lines))

    def next_char(self) -> Optional[str]:
        s = self.session
        if s is None or s.finished or s.position >= len(s.target):
            return None
        return s.target[s.position]

    def progress(self) -> float:
        s = self.session
        if not s:
            return 0.0
        if s.time_limit:
            return s.elapsed() / s.time_limit
        return s.position / max(1, len(s.target))

    # --- input -------------------------------------------------------------
    def focusNextPrevChild(self, next: bool) -> bool:
        return False  # keep Tab for "new text"

    def keyPressEvent(self, e: QKeyEvent) -> None:
        key, mods = e.key(), e.modifiers()
        if key == Qt.Key_Tab:
            self.restart.emit(True)
            return
        if key == Qt.Key_Escape:
            self.restart.emit(False)
            return
        s = self.session
        if s is None or s.finished:
            return
        if mods & Qt.ControlModifier and key != Qt.Key_Backspace:
            return  # ignore Cmd shortcuts (Qt maps Cmd to Control on macOS)
        if key == Qt.Key_Backspace:
            s.backspace(word=bool(mods & (Qt.AltModifier | Qt.ControlModifier)))
            self.keystroke.emit("backspace", True)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._type("\n")
        else:
            text = e.text()
            if not text or not all(c.isprintable() for c in text):
                return super().keyPressEvent(e)
            for c in text:
                self._type(c)
        self._after_input()

    def inputMethodEvent(self, e: QInputMethodEvent) -> None:
        if self.session and e.commitString():
            for c in e.commitString():
                self._type(c)
            self._after_input()
        e.accept()

    def inputMethodQuery(self, query):
        if query == Qt.ImEnabled:
            return True
        if query == Qt.ImCursorRectangle:
            return QRectF(self._caret_x.value, self._caret_y.value, 2, self.line_h).toRect()
        return super().inputMethodQuery(query)

    def _type(self, c: str) -> None:
        s = self.session
        if not s or s.finished:
            return
        expected = self.next_char()
        s.type_char(c)
        if expected is not None:
            self.keystroke.emit(c, c == expected)

    def _after_input(self) -> None:
        self._last_input = time.monotonic()
        first = self._first_line()
        if first != round(self._scroll.value):
            self._scroll.to(first)
        x, y = self._caret_pos(first)
        self._caret_x.to(x)
        self._caret_y.to(y)
        self._progress.to(self.progress())
        self.update()
        self.typed.emit()

    def tick(self) -> None:
        """Called by the page timer so the time-based progress line keeps moving."""
        if self.session and self.session.time_limit:
            self._progress.set(self.progress())

    # --- layout --------------------------------------------------------------
    def _relayout(self) -> None:
        if not self.session:
            return
        self._cols = max(8, int((self.width() - 2 * self.margin_x) // self.char_w))
        self._lines = wrap(self.session.target, self._cols)

    def _caret_line(self) -> int:
        pos = self.session.position
        return next((n for n, (a, b) in enumerate(self._lines) if a <= pos < b), len(self._lines) - 1)

    def _first_line(self) -> int:
        """The top visible line: keeps the line being typed near the top, with the
        upcoming line always visible below it (never typing on the last visible row)."""
        lead = 1 if self.visible_lines <= 4 else self.visible_lines // 3
        lead = max(0, min(lead, self.visible_lines - 2))
        return max(0, min(self._caret_line() - lead, len(self._lines) - self.visible_lines))

    def _caret_pos(self, first: float) -> tuple[float, float]:
        """Caret position in text coordinates (y relative to the first line of the text)."""
        n = self._caret_line()
        a = self._lines[n][0]
        return self.margin_x + (self.session.position - a) * self.char_w, n * self.line_h

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.session:
            self._fit_lines()
            self._relayout()
            first = self._first_line()
            self._scroll.set(first)
            x, y = self._caret_pos(first)
            self._caret_x.set(x)
            self._caret_y.set(y)

    # --- painting ----------------------------------------------------------
    def paintEvent(self, _event) -> None:
        if not self.session or not self._lines:
            return
        s = self.session
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Progress line
        track = QRectF(self.margin_x, 2, self.width() - 2 * self.margin_x, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(t.SURFACE_2)
        p.drawRoundedRect(track, 1.5, 1.5)
        done = QRectF(track.left(), track.top(), track.width() * min(1.0, self._progress.value), 3)
        if done.width() > 0:
            p.setBrush(t.TEXT)
            p.drawRoundedRect(done, 1.5, 1.5)

        focused = self.hasFocus()
        area = QRectF(0, self.top, self.width(), self.line_h * self.visible_lines)
        p.setClipRect(area.adjusted(-4, -6, 4, 6))
        scroll_y = self._scroll.value * self.line_h
        ascent = self.metrics.ascent()
        pad = (self.line_h - self.metrics.height()) / 2
        untyped = t.DIM
        p.setFont(self.font_)

        first_drawn = max(0, int(self._scroll.value) - 1)
        last_drawn = min(len(self._lines), int(self._scroll.value) + self.visible_lines + 2)
        for n in range(first_drawn, last_drawn):
            a, b = self._lines[n]
            top = self.top + n * self.line_h - scroll_y
            # Fade lines as they scroll out of the window.
            rel = (top - self.top) / self.line_h
            fade = 1.0
            if rel < 0:
                fade = max(0.0, 1 + rel)
            elif rel > self.visible_lines - 1:
                fade = max(0.0, self.visible_lines - rel)
            if not focused:
                fade *= 0.25
            if fade <= 0:
                continue
            for i in range(a, b):
                ch = s.target[i]
                x = self.margin_x + (i - a) * self.char_w
                base = top + pad + ascent
                cell = QRectF(x, top + pad, self.char_w, self.metrics.height())
                glyph = "↵" if ch == "\n" else ch
                if i < s.position:
                    if s.is_correct_at(i):
                        color = t.TEXT
                    else:
                        color = t.BAD
                        p.setPen(Qt.NoPen)
                        p.setBrush(t.alpha(t.BAD, 0.12 * fade))
                        p.drawRoundedRect(cell.adjusted(0, -2, 0, 2), 4, 4)
                        typed = s.typed[i][0]
                        if ch in " \n" and typed.strip():
                            glyph = typed  # show what was typed where a space was due
                else:
                    color = untyped
                if ch == "\n":
                    color = t.alpha(color, 0.5)
                p.setPen(t.alpha(color, color.alphaF() * fade))
                p.drawText(QPointF(x, base), glyph)

        # Caret: a solid orange bar that fades in and out while idle.
        if not s.finished and focused:
            idle = time.monotonic() - self._last_input
            a = 1.0 if idle < 0.6 else 0.15 + 0.85 * math.cos((idle - 0.6) * math.pi * 1.6) ** 2
            cx = self._caret_x.value
            cy = self.top + self._caret_y.value - scroll_y
            bar = QRectF(cx - 1.25, cy + pad + 3, 2.5, self.metrics.height() - 6)
            p.setPen(Qt.NoPen)
            p.setBrush(t.alpha(t.ACCENT, a))
            p.drawRoundedRect(bar, 1.25, 1.25)
        p.setClipping(False)

        if not focused:
            p.setPen(t.TEXT)
            p.setFont(t.ui(15, QFont.DemiBold))
            p.drawText(area, Qt.AlignCenter, "Click to keep typing")
        p.end()

    def focusInEvent(self, e) -> None:
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self.update()
