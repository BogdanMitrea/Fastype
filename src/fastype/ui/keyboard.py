"""An on-screen MacBook keyboard that matches the layout macOS is using.

Keys are physical keys (virtual key codes); their labels come from the current system
layout, so switching to German shows Z/Y swapped, Ü Ö Ä and ß, and an ISO keyboard gets
its extra key and tall Return. The widget notices layout switches on its own.

In live mode it lights up the next key to press (and which Shift or Option to hold, on the
other hand) and flashes keys green or red as you type. In heatmap mode each key is tinted
by its error rate.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..engine import KeyStat
from . import theme as t
from .layout import OPTION, RETURN, SHIFT, SPACE, KeyLayout, current_layout, current_source_id
from .widgets import Tween

DELETE, TAB, CAPS, SHIFT_L, SHIFT_R = 51, 48, 57, 56, 60
FN, CTRL, OPT_L, CMD_L, CMD_R, OPT_R, LEFT, UPDOWN, RIGHT = 63, 59, 58, 55, 54, 61, 123, 126, 124
NAMES = {DELETE: ("delete", "⌫"), TAB: ("tab", "⇥"), CAPS: ("caps lock", "⇪"), RETURN: ("return", "⏎"),
         SHIFT_L: ("shift", "⇧"), SHIFT_R: ("shift", "⇧"), FN: ("fn", "fn")}
SYMBOLS = {CTRL: "⌃", OPT_L: "⌥", OPT_R: "⌥", CMD_L: "⌘", CMD_R: "⌘",
           LEFT: "◀", UPDOWN: "▲▼", RIGHT: "▶"}
RIGHT_ALIGNED = {DELETE, RETURN, SHIFT_R}
LEFT_HAND = {50, 10, 18, 19, 20, 21, 23, 12, 13, 14, 15, 17, 0, 1, 2, 3, 5, 6, 7, 8, 9, 11}
HOME_BUMPS = {3, 38}  # the F and J positions
BOTTOM_ROW = [(FN, 1), (CTRL, 1), (OPT_L, 1), (CMD_L, 1.25), (SPACE, 5), (CMD_R, 1.25), (OPT_R, 1),
              (LEFT, 1), (UPDOWN, 1), (RIGHT, 1)]
# Rows of (key code, width in key units). The ISO Return is added separately (it spans two rows).
ANSI_ROWS = [
    [(c, 1) for c in (50, 18, 19, 20, 21, 23, 22, 26, 28, 25, 29, 27, 24)] + [(DELETE, 1.5)],
    [(TAB, 1.5)] + [(c, 1) for c in (12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 33, 30, 42)],
    [(CAPS, 1.75)] + [(c, 1) for c in (0, 1, 2, 3, 5, 4, 38, 40, 37, 41, 39)] + [(RETURN, 1.75)],
    [(SHIFT_L, 2.25)] + [(c, 1) for c in (6, 7, 8, 9, 11, 45, 46, 43, 47, 44)] + [(SHIFT_R, 2.25)],
    BOTTOM_ROW,
]
ISO_ROWS = [
    [(c, 1) for c in (10, 18, 19, 20, 21, 23, 22, 26, 28, 25, 29, 27, 24)] + [(DELETE, 1.5)],
    [(TAB, 1.5)] + [(c, 1) for c in (12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 33, 30)],
    [(CAPS, 1.75)] + [(c, 1) for c in (0, 1, 2, 3, 5, 4, 38, 40, 37, 41, 39, 42)],
    [(SHIFT_L, 1.25)] + [(c, 1) for c in (50, 6, 7, 8, 9, 11, 45, 46, 43, 47, 44)] + [(SHIFT_R, 2.25)],
    BOTTOM_ROW,
]
FLASH_MS = 380


class KeyboardWidget(QWidget):
    def __init__(self, heatmap: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.heatmap = heatmap
        self.layout_info: KeyLayout = current_layout()
        self.raw_stats: dict[str, KeyStat] = {}
        self.stats: dict[int, KeyStat] = {}
        self.shapes: dict[int, list[QRectF]] = {}  # one rect per key, two for the ISO Return
        self.rects: dict[int, QRectF] = {}         # bounding rect per key
        self.unit = 40.0
        self.next_char: Optional[str] = None
        self.next_key: Optional[int] = None
        self.modifier_keys: list[int] = []
        self._from: Optional[QRectF] = None
        self._move = Tween(self.update, 110, 1.0)
        self.flashes: dict[int, tuple[bool, float]] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._animate)
        # Notice when the user switches keyboard layouts (menu bar, Ctrl+Space, …).
        self._layout_timer = QTimer(self)
        self._layout_timer.setInterval(1000)
        self._layout_timer.timeout.connect(self._check_layout)
        self._layout_timer.start()
        self.setMouseTracking(heatmap)
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # --- system layout ----------------------------------------------------------
    def _check_layout(self) -> None:
        if self.isVisible() and current_source_id() != self.layout_info.source_id:
            self.reload_layout()

    def reload_layout(self) -> None:
        self.layout_info = current_layout()
        self._layout()
        self.set_stats(self.raw_stats)
        self.next_key = None
        self.set_next(self.next_char)

    # --- live mode -----------------------------------------------------------
    def set_next(self, ch: Optional[str]) -> None:
        self.next_char = ch
        found = self.layout_info.find(ch) if ch else None
        key, mods = found if found else (None, 0)
        if key != self.next_key:
            self._from = self._current_highlight()
            self.next_key = key
            self._move.to(1.0, 0.0)
        # Hold modifiers with the other hand: Shift/Option on the side away from the key.
        left = key in LEFT_HAND
        self.modifier_keys = []
        if mods & SHIFT:
            self.modifier_keys.append(SHIFT_R if left else SHIFT_L)
        if mods & OPTION:
            self.modifier_keys.append(OPT_R if left else OPT_L)
        self.update()

    def flash(self, ch: str, correct: bool) -> None:
        if ch == "backspace":
            key = DELETE
        else:
            found = self.layout_info.find(ch)
            key = found[0] if found else None
        if key in self.rects:
            self.flashes[key] = (correct, time.monotonic())
            if not self._timer.isActive():
                self._timer.start()

    def _animate(self) -> None:
        now = time.monotonic()
        self.flashes = {k: v for k, v in self.flashes.items() if (now - v[1]) * 1000 < FLASH_MS}
        if not self.flashes:
            self._timer.stop()
        self.update()

    def _current_highlight(self) -> Optional[QRectF]:
        if self.next_key is None or self.next_key not in self.rects:
            return None
        to = self.rects[self.next_key]
        if self._from is None or self._move.value >= 1:
            return QRectF(to)
        k = self._move.value
        f = self._from
        return QRectF(f.x() + (to.x() - f.x()) * k, f.y() + (to.y() - f.y()) * k,
                      f.width() + (to.width() - f.width()) * k, f.height() + (to.height() - f.height()) * k)

    # --- heatmap mode ---------------------------------------------------------
    def set_stats(self, stats: dict[str, KeyStat]) -> None:
        """Group per-character stats by the physical key that types them."""
        self.raw_stats = stats
        merged: dict[int, KeyStat] = {}
        for ch, s in stats.items():
            found = self.layout_info.find(ch)
            if not found:
                continue
            m = merged.setdefault(found[0], KeyStat())
            m.hits += s.hits
            m.misses += s.misses
            m.latency_total += s.latency_total
            m.latency_count += s.latency_count
        self.stats = merged
        self.update()

    def _rate(self, key: int) -> Optional[float]:
        s = self.stats.get(key)
        if not s or s.hits + s.misses == 0:
            return None
        return s.misses / (s.hits + s.misses)

    # --- layout & painting ------------------------------------------------------
    def _layout(self) -> None:
        caption = 18
        self.unit = min(self.width() / 14.6, (self.height() - caption - 4) / 5.05, 64.0)
        u, gap = self.unit, self.unit * 0.1
        x0 = (self.width() - 14.5 * u) / 2
        y0 = caption + (self.height() - caption - 5 * u) / 2
        self.shapes = {}
        for r, row in enumerate(ISO_ROWS if self.layout_info.iso else ANSI_ROWS):
            x = x0
            for key, w in row:
                self.shapes[key] = [QRectF(x + gap / 2, y0 + r * u + gap / 2, w * u - gap, u - gap)]
                x += w * u
        if self.layout_info.iso:  # tall Return: wide at the top, narrower below
            top = QRectF(x0 + 13.5 * u + gap / 2, y0 + u + gap / 2, u - gap, u)
            bottom = QRectF(x0 + 13.75 * u + gap / 2, y0 + 1.5 * u, 0.75 * u - gap, 1.5 * u - gap)
            self.shapes[RETURN] = [top, bottom]
        self.rects = {k: _bounds(v) for k, v in self.shapes.items()}
        self._caption_rect = QRectF(x0, 0, 14.5 * u, caption)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._layout()

    def paintEvent(self, _e) -> None:
        if not self.rects:
            self._layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        u = self.unit
        radius = u * 0.16
        now = time.monotonic()
        lay = self.layout_info

        p.setPen(t.MUTED)
        p.setFont(t.ui(10.5))
        p.drawText(self._caption_rect, Qt.AlignRight | Qt.AlignVCenter,
                   f"{lay.name}  ·  {'ISO' if lay.iso else 'ANSI'}")

        for key, shape in self.shapes.items():
            fill, edge, depth = t.KEY, t.KEY_EDGE, max(2.0, u * 0.07)
            is_char = key not in NAMES and key not in SYMBOLS
            text_c = t.TEXT if is_char else t.MUTED
            rate = self._rate(key) if self.heatmap else None
            if rate is not None:
                heat = min(1.0, rate / 0.12)
                fill = t.mix(t.mix(t.KEY, t.GOOD, 0.12), t.BAD, heat * 0.85)
                edge = t.mix(t.KEY_EDGE, t.BAD, heat * 0.6)
                text_c = t.mix(t.TEXT, t.KEY, heat * 0.9)
            if key in self.flashes:
                ok, start = self.flashes[key]
                k = 1 - (now - start) * 1000 / FLASH_MS
                fill = t.mix(fill, t.mix(t.KEY, t.GOOD if ok else t.BAD, 0.35), k)
                depth *= 1 - 0.7 * k  # the key looks pressed down, then springs back
            rect = _keycap(p, shape, radius, fill, edge, depth)
            self._label(p, key, rect, text_c)

            if key in HOME_BUMPS:
                p.setPen(QPen(t.alpha(t.MUTED, 0.6), max(1.5, u * 0.04), Qt.SolidLine, Qt.RoundCap))
                cx, by = rect.center().x(), rect.bottom() - u * 0.16
                p.drawLine(QPointF(cx - u * 0.1, by), QPointF(cx + u * 0.1, by))
            if rate is not None and is_char and key != SPACE:
                p.setPen(t.alpha(text_c, 0.75))
                p.setFont(t.ui(max(7, u * 0.16), QFont.DemiBold))
                p.drawText(rect.adjusted(0, 0, -u * 0.1, -u * 0.06), Qt.AlignRight | Qt.AlignBottom, f"{rate:.0%}")

        if not self.heatmap:
            hl = self._current_highlight()
            if hl is not None:
                gliding = self._move.value < 1
                self._outline(p, [hl] if gliding else self.shapes[self.next_key], radius, 1.0)
            for m in self.modifier_keys:
                self._outline(p, self.shapes[m], radius, 0.7)
        p.end()

    def _label(self, p: QPainter, key: int, rect: QRectF, color) -> None:
        u = self.unit
        p.setPen(color)
        if key in SYMBOLS:
            p.setFont(t.ui(max(9, u * (0.3 if key in (CTRL, OPT_L, OPT_R, CMD_L, CMD_R) else 0.2))))
            p.drawText(rect, Qt.AlignCenter, SYMBOLS[key])
        elif key in NAMES:
            word, short = NAMES[key]
            p.setFont(t.ui(max(7.5, u * 0.19), QFont.Medium))
            if p.fontMetrics().horizontalAdvance(word) > rect.width() - u * 0.3:
                word = short  # too small for the word
            if key == RETURN and self.layout_info.iso:
                rect = QRectF(rect.left(), rect.top(), rect.width(), u * 0.9)
            align = Qt.AlignRight if key in RIGHT_ALIGNED else Qt.AlignLeft
            p.drawText(rect.adjusted(u * 0.14, 0, -u * 0.14, -u * 0.1), align | Qt.AlignBottom, word)
        elif key != SPACE:
            main, shifted = self.layout_info.label(key)
            if shifted:
                p.setFont(t.ui(max(8, u * 0.24), QFont.Medium))
                p.drawText(rect.adjusted(0, u * 0.08, 0, -rect.height() / 2), Qt.AlignHCenter | Qt.AlignBottom, shifted)
                p.drawText(rect.adjusted(0, rect.height() / 2, 0, -u * 0.08), Qt.AlignHCenter | Qt.AlignTop, main)
            else:
                p.setFont(t.ui(max(8, u * 0.3), QFont.Medium))
                p.drawText(rect, Qt.AlignCenter, main)

    def _outline(self, p: QPainter, rects: list[QRectF], radius: float, strength: float) -> None:
        p.setBrush(t.alpha(t.ACCENT, 0.14 * strength))
        p.setPen(QPen(t.alpha(t.ACCENT, strength), 1.6))
        p.drawPath(_shape_path([r.adjusted(0.5, 0.5, -0.5, -0.5) for r in rects], radius))

    def mouseMoveEvent(self, e) -> None:
        for key, rect in self.rects.items():
            if key in NAMES and key != RETURN or key in SYMBOLS or not rect.contains(e.position()):
                continue
            s = self.stats.get(key)
            name = {SPACE: "space", RETURN: "return"}.get(key) or self.layout_info.label(key)[0]
            if s and s.hits + s.misses:
                total = s.hits + s.misses
                tip = f"{name}: {s.misses} missed of {total} ({s.misses / total:.1%})"
                if s.latency_count:
                    tip += f"\n{1000 * s.latency_total / s.latency_count:.0f} ms on average"
            else:
                tip = f"{name}: no data yet"
            QToolTip.showText(e.globalPosition().toPoint(), tip, self)
            return
        QToolTip.hideText()


def _bounds(rects: list[QRectF]) -> QRectF:
    r = QRectF(rects[0])
    for other in rects[1:]:
        r = r.united(other)
    return r


def _shape_path(rects: list[QRectF], radius: float) -> QPainterPath:
    path = QPainterPath()
    for r in rects:
        part = QPainterPath()
        part.addRoundedRect(r, radius, radius)
        path = path.united(part)
    return path


def _keycap(p: QPainter, rects: list[QRectF], radius: float, face, edge, depth: float) -> QRectF:
    """A matte keycap of any shape (the ISO Return is two rects). Returns the face bounds."""
    if len(rects) == 1:
        return t.keycap(p, rects[0], radius, face, edge, depth)
    p.setPen(Qt.NoPen)
    p.setBrush(edge)
    p.drawPath(_shape_path(rects, radius))
    face_rects = rects[:-1] + [rects[-1].adjusted(0, 0, 0, -depth)]
    p.setPen(QPen(t.alpha(edge, 0.7), 1))
    p.setBrush(face)
    p.drawPath(_shape_path([r.adjusted(0.5, 0.5, -0.5, -0.5) for r in face_rects], radius))
    return _bounds(face_rects)
