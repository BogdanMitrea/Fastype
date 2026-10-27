"""Progress screen: totals, speed history, practice calendar and the keyboard heatmap."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from ..store import Store
from . import theme as t
from .charts import ActivityGrid, AreaChart, HourChart
from .keyboard import KeyboardWidget
from .widgets import Chip, StatCard


class Panel(QWidget):
    """A card with a title that holds another widget."""

    def __init__(self, title: str, body: QWidget, subtitle: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.title, self.subtitle = title, subtitle
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 46, 20, 16)
        lay.addWidget(body)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t.card(p, QRectF(self.rect()), 18)
        p.setPen(t.TEXT)
        p.setFont(t.ui(14, QFont.DemiBold))
        p.drawText(QRectF(20, 16, self.width() - 40, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        if self.subtitle:
            p.setPen(t.MUTED)
            p.setFont(t.ui(11.5))
            p.drawText(QRectF(20, 16, self.width() - 40, 22), Qt.AlignRight | Qt.AlignVCenter, self.subtitle)


class ProgressPage(QWidget):
    def __init__(self, store: Store, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self.cards = {
            "sessions": StatCard("Runs"),
            "best": StatCard("Best", suffix="wpm"),
            "recent": StatCard("Last 10 avg", suffix="wpm"),
            "accuracy": StatCard("Accuracy", "{:.1f}", "%"),
            "minutes": StatCard("Practised", suffix="min"),
            "streak": StatCard("Day streak", suffix="days"),
        }
        self.cards["best"].highlight = True
        cards = QHBoxLayout()
        cards.setSpacing(12)
        for c in self.cards.values():
            cards.addWidget(c)

        self.chart = AreaChart(min_height=200)
        self.chart.empty_text = "Finish a run and your speed shows up here"
        self.activity = ActivityGrid()
        self.hours = HourChart()
        self.heatmap = KeyboardWidget(heatmap=True)
        self.heatmap.setMinimumHeight(250)
        self.slow = QLabel()
        self.slow.setObjectName("muted")
        reset = Chip("reset statistics")
        reset.setCheckable(False)
        reset.clicked.connect(self._reset)

        kb_box = QWidget()
        kb_lay = QVBoxLayout(kb_box)
        kb_lay.setContentsMargins(0, 0, 0, 0)
        kb_lay.addWidget(self.heatmap)
        kb_lay.addWidget(self.slow)

        self.chart_panel = Panel("Speed", self.chart, "last 100 runs  ·  dashed: raw speed, mistakes included")
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.addWidget(self.chart_panel, 0, 0, 1, 2)
        grid.addWidget(Panel("Accuracy by time of day", self.hours, "orange: your most accurate hour  ·  faint: under 3 runs"), 1, 0, 1, 2)
        grid.addWidget(Panel("Practice calendar", self.activity, "last 6 months"), 2, 0, 1, 2)
        grid.addWidget(Panel("Where your errors happen", kb_box, "hover a key for details"), 3, 0, 1, 2)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(36, 8, 36, 20)
        lay.addLayout(cards)
        lay.addSpacing(14)
        lay.addLayout(grid)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(reset)
        lay.addSpacing(10)
        lay.addLayout(foot)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self) -> None:
        s = self.store.summary()
        sessions = self.store.sessions(1000)
        recent = sessions[-10:]
        days = {dt.date.fromtimestamp(r.started_at) for r in sessions}
        streak, day = 0, dt.date.today()
        if day not in days:
            day -= dt.timedelta(days=1)  # today not practised yet doesn't break the streak
        while day in days:
            streak += 1
            day -= dt.timedelta(days=1)
        values = {
            "sessions": s["sessions"], "best": s["best_wpm"],
            "recent": sum(r.wpm for r in recent) / len(recent) if recent else 0,
            "accuracy": s["avg_accuracy"], "minutes": s["total_seconds"] / 60, "streak": streak,
        }
        self.cards["streak"].suffix = "day" if streak == 1 else "days"
        for k, v in values.items():
            self.cards[k].set_value(v)

        last = sessions[-100:]
        self.chart.set_values([r.wpm for r in last], "older  →  newer",
                              secondary=[r.raw_wpm for r in last])
        self.activity.set_sessions(sessions)
        self.hours.set_data(self.store.accuracy_by_hour())
        stats = self.store.key_stats()
        self.heatmap.set_stats(stats)
        timed = {c: st.latency_total / st.latency_count for c, st in stats.items()
                 if st.latency_count >= 10 and c.strip()}
        slowest = sorted(timed, key=lambda c: -timed[c])[:6]
        self.slow.setText(
            "Slowest keys:   " + "    ".join(f"<b>{c.upper()}</b> {1000 * timed[c]:.0f} ms"
                                            for c in slowest)
            if slowest else "Your slowest keys will show here after a few runs."
        )

    def _reset(self) -> None:
        if QMessageBox.question(self, "Reset statistics",
                                "Delete all run history and key statistics?") == QMessageBox.Yes:
            self.store.reset()
            self.refresh()
