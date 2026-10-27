"""Hand-drawn charts: an area chart for speed and a calendar of practice days."""
from __future__ import annotations

import datetime as dt
import math
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import theme as t
from .widgets import Tween


def nice_max(v: float) -> float:
    """Top of the axis, chosen so the four grid steps are round numbers."""
    for step in (5, 10, 20, 25, 50, 100):
        if v * 1.1 <= step * 4:
            return step * 4
    return math.ceil(v * 1.1 / 100) * 100


def _smooth_path(points: list[QPointF]) -> QPainterPath:
    """A curve through the points (Catmull-Rom turned into cubic Béziers)."""
    path = QPainterPath(points[0])
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = p1 + (p2 - p0) / 6
        c2 = p2 - (p3 - p1) / 6
        path.cubicTo(c1, c2, p2)
    return path


class AreaChart(QWidget):
    """Speed over time: an ink line over a light fill, revealed left to right."""

    def __init__(self, parent: Optional[QWidget] = None, min_height: int = 160):
        super().__init__(parent)
        self.values: list[float] = []
        self.secondary: list[float] = []
        self.x_label = ""
        self.empty_text = "No data yet"
        self._reveal = Tween(self.update, 900, 1.0, QEasingCurve.OutQuart)
        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_values(self, values: list[float], x_label: str = "", secondary: list[float] = ()) -> None:
        self.values = list(values)
        self.secondary = list(secondary)
        self.x_label = x_label
        self._reveal.to(1.0, 0.0)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(t.ui(10.5))
        plot = QRectF(self.rect()).adjusted(40, 12, -14, -26)
        if not self.values:
            p.setPen(t.MUTED)
            p.setFont(t.ui(13))
            p.drawText(self.rect(), Qt.AlignCenter, self.empty_text)
            return
        top = nice_max(max(self.values + self.secondary))
        for k in range(5):
            y = plot.bottom() - plot.height() * k / 4
            p.setPen(QPen(t.BORDER, 1, Qt.DotLine if k else Qt.SolidLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(t.MUTED)
            p.drawText(QRectF(0, y - 8, plot.left() - 10, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"{top * k / 4:.0f}")
        if self.x_label:
            p.drawText(QRectF(plot.left(), plot.bottom() + 6, plot.width(), 16), Qt.AlignCenter, self.x_label)

        def points(vals: list[float]) -> list[QPointF]:
            n = len(vals)
            return [QPointF(plot.left() + (plot.width() * i / (n - 1) if n > 1 else plot.width() / 2),
                            plot.bottom() - plot.height() * v / top) for i, v in enumerate(vals)]

        p.setClipRect(QRectF(0, 0, plot.left() + plot.width() * self._reveal.value + 8, self.height()))
        if len(self.secondary) > 1:
            p.setPen(QPen(t.alpha(t.MUTED, 0.6), 1.2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawPath(_smooth_path(points(self.secondary)))

        pts = points(self.values)
        if len(pts) == 1:
            pts = [QPointF(plot.left(), pts[0].y()), QPointF(plot.right(), pts[0].y())]
        line = _smooth_path(pts)
        area = QPainterPath(line)
        area.lineTo(pts[-1].x(), plot.bottom())
        area.lineTo(pts[0].x(), plot.bottom())
        area.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(t.alpha(t.TEXT, 0.05))
        p.drawPath(area)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(t.TEXT, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(line)

        best = max(range(len(self.values)), key=lambda i: self.values[i])
        bp = points(self.values)[best]
        if bp.x() <= plot.left() + plot.width() * self._reveal.value + 1:
            p.setPen(QPen(t.SURFACE, 2))
            p.setBrush(t.ACCENT)
            p.drawEllipse(bp, 5, 5)
            p.setPen(t.ACCENT)
            p.setFont(t.ui(10.5, QFont.DemiBold))
            label = QRectF(bp.x() - 60, bp.y() - 24, 120, 16)
            label.moveLeft(min(max(label.left(), plot.left()), plot.right() - 120))
            p.drawText(label, Qt.AlignCenter, f"best {self.values[best]:.0f}")
        p.end()


class HourChart(QWidget):
    """Accuracy for each hour of the day as 24 bars. Hours with few runs are drawn faint."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.data: dict[int, tuple[float, int, int]] = {}
        self.bars: list[tuple[QRectF, int]] = []
        self._grow = Tween(self.update, 700, 1.0, QEasingCurve.OutCubic)
        self.setMouseTracking(True)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, data: dict[int, tuple[float, int, int]]) -> None:
        self.data = data
        self._grow.to(1.0, 0.0)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plot = QRectF(self.rect()).adjusted(48, 10, -14, -24)
        if not self.data:
            p.setPen(t.MUTED)
            p.setFont(t.ui(13))
            p.drawText(self.rect(), Qt.AlignCenter, "Finish a few runs and your accuracy by hour shows up here")
            return
        # Zoom the axis in on where the values are, so a few percent difference is visible.
        # Four round steps down from 100% that still leave room under the lowest bar.
        lowest = min(acc for acc, _, _ in self.data.values())
        step = next(s for s in (1, 2, 3, 5, 10, 25) if 100 - 4 * s <= lowest - 1)
        floor_ = 100.0 - 4 * step
        p.setFont(t.ui(10.5))
        for k in range(5):
            v = floor_ + (100 - floor_) * k / 4
            y = plot.bottom() - plot.height() * k / 4
            p.setPen(QPen(t.BORDER, 1, Qt.DotLine if k else Qt.SolidLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(t.MUTED)
            p.drawText(QRectF(0, y - 8, plot.left() - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:.0f}%")

        slot = plot.width() / 24
        best = max(self.data, key=lambda h: self.data[h][0])
        self.bars = []
        for h in range(24):
            x = plot.left() + h * slot
            if h % 3 == 0:
                p.setPen(t.MUTED)
                p.drawText(QRectF(x - slot, plot.bottom() + 4, slot * 3, 16), Qt.AlignHCenter | Qt.AlignTop, f"{h:02d}")
            bar_w = slot * 0.62
            cx = x + slot / 2
            if h not in self.data:
                p.setPen(Qt.NoPen)
                p.setBrush(t.SURFACE_2)
                p.drawEllipse(QPointF(cx, plot.bottom() - 3), 2, 2)
                self.bars.append((QRectF(x, plot.top(), slot, plot.height()), h))
                continue
            acc, runs, _ = self.data[h]
            height = max(3.0, plot.height() * (acc - floor_) / (100 - floor_)) * self._grow.value
            bar = QRectF(cx - bar_w / 2, plot.bottom() - height, bar_w, height)
            color = t.ACCENT if h == best else t.TEXT
            p.setPen(Qt.NoPen)
            p.setBrush(t.alpha(color, 0.85 if runs >= 3 else 0.3))
            p.drawRoundedRect(bar, min(4, bar_w / 3), min(4, bar_w / 3))
            self.bars.append((QRectF(x, plot.top(), slot, plot.height()), h))
        p.end()

    def mouseMoveEvent(self, e) -> None:
        for r, h in self.bars:
            if r.contains(e.position()):
                if h in self.data:
                    acc, runs, keys = self.data[h]
                    tip = (f"{h:02d}:00–{(h + 1) % 24:02d}:00\n{acc:.1f}% accurate over {runs} "
                           f"run{'s' if runs != 1 else ''} ({keys:,} keys)")
                    if runs < 3:
                        tip += "\nfew runs yet, so take this one lightly"
                else:
                    tip = f"{h:02d}:00–{(h + 1) % 24:02d}:00\nno runs yet"
                QToolTip.showText(e.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()


class ActivityGrid(QWidget):
    """Minutes practised per day for the last few months, one square per day."""

    WEEKS = 26

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.minutes: dict[dt.date, float] = {}
        self.cells: list[tuple[QRectF, dt.date]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(175)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_sessions(self, sessions) -> None:
        self.minutes = {}
        for s in sessions:
            day = dt.date.fromtimestamp(s.started_at)
            self.minutes[day] = self.minutes.get(day, 0.0) + s.duration / 60
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        today = dt.date.today()
        start = today - dt.timedelta(days=today.weekday() + 7 * (self.WEEKS - 1))
        label_w = 36
        cell = min((self.width() - label_w) / self.WEEKS, (self.height() - 20) / 7)
        size = cell * 0.8
        x0 = label_w + (self.width() - label_w - cell * self.WEEKS) / 2
        p.setFont(t.ui(9.5))
        p.setPen(t.MUTED)
        for row, name in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
            p.drawText(QRectF(x0 - label_w, 18 + row * cell, label_w - 6, size), Qt.AlignRight | Qt.AlignVCenter, name)
        self.cells = []
        last_month = None
        for w in range(self.WEEKS):
            monday = start + dt.timedelta(weeks=w)
            if monday.month != last_month:
                last_month = monday.month
                p.setPen(t.MUTED)
                p.drawText(QPointF(x0 + w * cell, 12), monday.strftime("%b"))
            for d in range(7):
                day = monday + dt.timedelta(days=d)
                if day > today:
                    continue
                r = QRectF(x0 + w * cell, 18 + d * cell, size, size)
                mins = self.minutes.get(day, 0.0)
                p.setPen(Qt.NoPen)
                if mins <= 0:
                    p.setBrush(t.SURFACE_2)
                else:
                    level = min(1.0, 0.25 + mins / 15)  # 15+ minutes = darkest
                    p.setBrush(t.mix(t.ACCENT_SOFT, t.ACCENT, level))
                p.drawRoundedRect(r, size * 0.22, size * 0.22)
                if day == today:
                    p.setPen(QPen(t.TEXT, 1.2))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(r, size * 0.22, size * 0.22)
                self.cells.append((r, day))
        p.end()

    def mouseMoveEvent(self, e) -> None:
        for r, day in self.cells:
            if r.contains(e.position()):
                mins = self.minutes.get(day, 0.0)
                text = f"{day:%a %d %b}: " + (f"{mins:.0f} min" if mins >= 1 else
                                               f"{mins * 60:.0f} s" if mins else "no practice")
                QToolTip.showText(e.globalPosition().toPoint(), text, self)
                return
        QToolTip.hideText()
