"""Entry point: the main window with Practice and Progress pages."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .settings import settings
from .store import Store
from .ui import theme as t
from .ui.practice import PracticePage, fade_in
from .ui.progress import ProgressPage
from .ui.widgets import Logo, PageSwitch, ThemeButton

ICON = Path(__file__).parent / "assets" / "icon.png"


class Backdrop(QWidget):
    """The window background: warm paper grey with a faint grain."""

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), t.BG)
        if not hasattr(self, "_grain"):
            self._grain = QPixmap.fromImage(t.grain())
        p.drawTiledPixmap(self.rect(), self._grain)


class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.setWindowTitle("Fastype")
        self.resize(1180, 820)
        self.setMinimumSize(980, 700)
        self.practice = PracticePage(store)
        self.progress = ProgressPage(store)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.practice)
        self.pages.addWidget(self.progress)

        self.switch = PageSwitch(["Practice", "Progress"])
        self.switch.changed.connect(self._page_changed)
        header = QHBoxLayout()
        header.setContentsMargins(36, 18, 36, 6)
        header.addWidget(Logo())
        header.addStretch(1)
        header.addWidget(self.switch)
        header.addStretch(1)
        self.theme_button = ThemeButton()
        self.theme_button.clicked.connect(lambda: self.set_dark(not t.dark))
        right = QHBoxLayout()  # as wide as the logo, so the page switch sits in the middle
        right.addStretch(1)
        right.addWidget(self.theme_button)
        holder = QWidget()
        holder.setFixedWidth(180)
        holder.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        header.addWidget(holder)

        root = Backdrop()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(header)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        # Shortcuts work wherever the focus is (the typing area takes plain key presses).
        for keys, action in (("Ctrl+1", lambda: self.switch.set_index(0)),
                             ("Ctrl+2", lambda: self.switch.set_index(1)),
                             ("Ctrl+Shift+L", lambda: self.set_dark(not t.dark))):
            QShortcut(QKeySequence(keys), self, activated=action)

    def set_dark(self, dark: bool) -> None:
        """Switch themes, cross-fading from a snapshot of the old look."""
        root = self.centralWidget()
        snapshot = root.grab() if self.isVisible() else None
        apply_theme(dark)
        settings().setValue("theme", "dark" if dark else "light")
        for w in self.findChildren(QWidget):
            w.update()
        if snapshot is None:
            return
        overlay = QLabel(root)
        overlay.setPixmap(snapshot)
        overlay.setGeometry(root.rect())
        overlay.show()
        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", overlay)
        anim.setDuration(280)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.finished.connect(overlay.deleteLater)
        anim.start()

    def _page_changed(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.progress.refresh()
        else:
            self.practice.new_run(False)
        fade_in(self.pages.currentWidget())



def apply_theme(dark: bool) -> None:
    app = QApplication.instance()
    t.apply(dark)
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)  # title bar
    app.setStyleSheet(t.stylesheet())


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Fastype")
    t.load_fonts()
    # First launch follows macOS; after that, whatever was picked last.
    saved = settings().value("theme")
    apply_theme(saved == "dark" if saved else app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))
    window = MainWindow(Store())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
