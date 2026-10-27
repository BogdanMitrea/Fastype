"""Small custom-painted controls: chips, the page switcher, the header and stat cards."""
from __future__ import annotations

import math
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QSizePolicy, QWidget

from . import theme as t


class Tween:
    """A number that glides to its new value and calls `on_change` on every frame."""

    def __init__(self, on_change: Callable[[], None], ms: int = 400, value: float = 0.0,
                 curve: QEasingCurve.Type = QEasingCurve.OutCubic):
        self.value = value
        self._anim = QVariantAnimation()
        self._anim.setDuration(ms)
        self._anim.setEasingCurve(curve)
        self._anim.valueChanged.connect(self._step)
        self._on_change = on_change

    def _step(self, v) -> None:
        self.value = float(v)
        self._on_change()

    def to(self, target: float, start: Optional[float] = None) -> None:
        self._anim.stop()
        self._anim.setStartValue(float(self.value if start is None else start))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def set(self, value: float) -> None:
        self._anim.stop()
        self.value = value
        self._on_change()


class Chip(QAbstractButton):
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = Tween(self.update, 160)
        self._on = Tween(self.update, 220)
        self.toggled.connect(lambda on: self._on.to(1.0 if on else 0.0))

    def sizeHint(self) -> QSize:
        w = QFontMetricsF(t.ui(12.5, QFont.Medium)).horizontalAdvance(self.text())
        return QSize(int(w + 30), 32)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def enterEvent(self, e) -> None:
        self._hover.to(1.0)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on, hover = self._on.value, self._hover.value
        p.setPen(Qt.NoPen)
        p.setBrush(t.mix(t.alpha(t.SURFACE_2, 0.0), t.TEXT, on) if on else t.alpha(t.SURFACE_2, hover))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(t.mix(t.mix(t.MUTED, t.TEXT, hover), t.SURFACE, on))
        p.setFont(t.ui(12.5, QFont.Medium))
        p.drawText(r, Qt.AlignCenter, self.text())


class ChipRow(QWidget):
    """A row of chips where exactly one is selected."""

    changed = Signal(str)

    def __init__(self, items: list[str] = (), current: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked.connect(lambda b: self.changed.emit(b.text()))
        self.set_items(list(items), current)

    def set_items(self, items: list[str], current: Optional[str] = None) -> None:
        for b in self._group.buttons():
            self._group.removeButton(b)
            b.deleteLater()
        for text in items:
            chip = Chip(text)
            self._group.addButton(chip)
            self._lay.addWidget(chip)
            if text == (current or items[0]):
                chip.setChecked(True)
                chip._on.set(1.0)

    def current(self) -> str:
        b = self._group.checkedButton()
        return b.text() if b else ""


class Toggle(Chip):
    """A chip that turns on and off on its own."""


class Divider(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(17, 32)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(QRectF(8, 8, 1, 16), t.BORDER)


class PageSwitch(QWidget):
    """Segmented control with a highlight that slides between pages."""

    changed = Signal(int)

    def __init__(self, items: list[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.items = items
        self.index = 0
        self._pos = Tween(self.update, 260)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(110 * len(items) + 8, 40)

    def set_index(self, i: int) -> None:
        if i != self.index:
            self.index = i
            self._pos.to(i)
            self.changed.emit(i)

    def mousePressEvent(self, e) -> None:
        self.set_index(min(len(self.items) - 1, int((e.position().x() - 4) // 110)))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(t.SURFACE_2)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        pill = QRectF(4 + self._pos.value * 110, 4, 110, r.height() - 8)
        t.card(p, pill, pill.height() / 2, t.KEY)
        p.setFont(t.ui(13, QFont.DemiBold))
        for i, text in enumerate(self.items):
            cell = QRectF(4 + i * 110, 4, 110, r.height() - 7)
            closeness = max(0.0, 1 - abs(self._pos.value - i))
            p.setPen(t.mix(t.MUTED, t.TEXT, closeness))
            p.drawText(cell, Qt.AlignCenter, text)


class Logo(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(180, 40)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        mark = QRectF(2, 6, 28, 29)
        face = t.keycap(p, mark, 7, t.TEXT, t.mix(t.TEXT, QColor("#000000"), 0.55), 3)
        p.setPen(Qt.NoPen)
        p.setBrush(t.ACCENT)
        p.drawRoundedRect(QRectF(face.center().x() - 1.75, face.top() + 6, 3.5, face.height() - 12), 1.5, 1.5)
        p.setPen(t.TEXT)
        p.setFont(t.ui(17, QFont.Bold, spacing=-0.3))
        p.drawText(QRectF(40, 0, 140, 40), Qt.AlignVCenter, "fastype")


class ThemeButton(QAbstractButton):
    """A round keycap showing a moon (switch to dark) or a sun (switch to light)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Switch between light and dark (⌘⇧L)")
        self.setFixedSize(38, 40)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        face = t.keycap(p, QRectF(1, 1, 36, 38), 18, depth=3 if not self.isDown() else 1)
        c = face.center()
        p.setPen(Qt.NoPen)
        p.setBrush(t.TEXT)
        if t.dark:  # sun
            p.drawEllipse(c, 4.5, 4.5)
            p.setPen(QPen(t.TEXT, 1.8, Qt.SolidLine, Qt.RoundCap))
            for i in range(8):
                a = i * math.pi / 4
                p.drawLine(QPointF(c.x() + 7.5 * math.cos(a), c.y() + 7.5 * math.sin(a)),
                           QPointF(c.x() + 10 * math.cos(a), c.y() + 10 * math.sin(a)))
        else:  # crescent moon
            moon = QPainterPath()
            moon.addEllipse(c, 8, 8)
            bite = QPainterPath()
            bite.addEllipse(QPointF(c.x() + 4.5, c.y() - 3.5), 7, 7)
            p.drawPath(moon.subtracted(bite))


class GuestBanner(QWidget):
    """A strip under the header while guest mode is on."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(40)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(36, 4, -36, -4)
        p.setPen(Qt.NoPen)
        p.setBrush(t.ACCENT_SOFT)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(t.TEXT)
        p.setFont(t.ui(12, QFont.Medium))
        p.drawText(r, Qt.AlignCenter,
                   "Guest mode  ·  runs are kept only until Fastype quits and never touch your own stats")


class StatCard(QWidget):
    """A small card with a caption and a big number that counts to its value."""

    def __init__(self, caption: str, fmt: str = "{:.0f}", suffix: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.caption, self.fmt, self.suffix = caption, fmt, suffix
        self.highlight = False
        self._v = Tween(self.update, 900)
        self.setMinimumSize(130, 88)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, v: float, animate: bool = True) -> None:
        self._v.to(v, 0.0) if animate else self._v.set(v)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        t.card(p, r, 14)
        if self.highlight:
            p.setPen(Qt.NoPen)
            p.setBrush(t.ACCENT)
            p.drawEllipse(QRectF(r.right() - 22, 17, 7, 7))
        p.setPen(t.MUTED)
        p.setFont(t.ui(10.5, QFont.DemiBold, spacing=1.2))
        p.drawText(r.adjusted(16, 14, -12, 0), Qt.AlignLeft | Qt.AlignTop, self.caption.upper())
        p.setPen(t.TEXT)
        p.setFont(t.mono(25, QFont.Medium))
        text = self.fmt.format(self._v.value)
        p.drawText(r.adjusted(16, 0, -12, -12), Qt.AlignLeft | Qt.AlignBottom, text)
        if self.suffix:
            w = p.fontMetrics().horizontalAdvance(text)
            p.setPen(t.MUTED)
            p.setFont(t.ui(13, QFont.Medium))
            p.drawText(r.adjusted(16 + w + 4, 0, -12, -15), Qt.AlignLeft | Qt.AlignBottom, self.suffix)


def hint_text(p: QPainter, rect: QRectF, parts: list[tuple[str, str]]) -> None:
    """Draws 'key  action · key  action' with the keys as small keycaps, centred."""
    p.setRenderHint(QPainter.Antialiasing)
    key_font, label_font = t.ui(11, QFont.DemiBold), t.ui(11.5)
    km, lm = QFontMetricsF(key_font), QFontMetricsF(label_font)
    widths = [km.horizontalAdvance(k) + 14 + 6 + lm.horizontalAdvance(a) for k, a in parts]
    total = sum(widths) + 26 * (len(parts) - 1)
    x = rect.center().x() - total / 2
    y = rect.center().y()
    for (k, a), w in zip(parts, widths):
        kw = km.horizontalAdvance(k) + 14
        cap = t.keycap(p, QRectF(x, y - 11, kw, 23), 5)
        p.setPen(t.TEXT)
        p.setFont(key_font)
        p.drawText(cap, Qt.AlignCenter, k)
        p.setPen(t.MUTED)
        p.setFont(label_font)
        p.drawText(QPointF(x + kw + 6, y + lm.ascent() / 2 - 1), a)
        x += w + 26
