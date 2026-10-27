"""Colours, fonts and small painting helpers shared by every screen.

The look is matte: warm paper-grey (or charcoal) surfaces, ink text, one orange accent,
keycap-like controls with a soft bottom edge. No glows or gradients.

Colours are module globals that `apply()` swaps between the light and dark palettes,
so painting code should always read them as `theme.X` at paint time.
"""
from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen

LIGHT = {
    "BG": "#ece9e3",
    "SURFACE": "#f6f4ef",      # cards
    "SURFACE_2": "#e2ded6",    # recessed tracks, empty cells
    "KEY": "#f9f8f5",          # keycap face
    "KEY_EDGE": "#cfc9be",     # keycap bottom edge
    "BORDER": "#d8d3c9",
    "TEXT": "#23211e",
    "MUTED": "#8a857b",
    "DIM": "#b3ada2",          # text not typed yet
    "ACCENT": "#d9622b",       # burnt orange
    "ACCENT_SOFT": "#f3d9c9",
    "GOOD": "#5f8a57",         # sage
    "BAD": "#c1453a",          # brick
    "SHADOW": "#0e3c321e",     # #AARRGGBB
}
DARK = {
    "BG": "#1c1b19",
    "SURFACE": "#252421",
    "SURFACE_2": "#2f2d2a",
    "KEY": "#353330",
    "KEY_EDGE": "#121110",
    "BORDER": "#3b3935",
    "TEXT": "#ebe7df",
    "MUTED": "#918b81",
    "DIM": "#5c5851",
    "ACCENT": "#e3733d",
    "ACCENT_SOFT": "#4b3124",
    "GOOD": "#83ab77",
    "BAD": "#dc5d4f",
    "SHADOW": "#50000000",
}

BG = SURFACE = SURFACE_2 = KEY = KEY_EDGE = BORDER = TEXT = MUTED = DIM = QColor()
ACCENT = ACCENT_SOFT = GOOD = BAD = SHADOW = QColor()
dark = False


def apply(is_dark: bool) -> None:
    """Switch every colour in this module to the light or dark palette."""
    global dark
    dark = is_dark
    for name, value in (DARK if is_dark else LIGHT).items():
        globals()[name] = QColor(value)


apply(False)

_mono_family = "Menlo"
_SF_MONO_DIR = Path("/System/Applications/Utilities/Terminal.app/Contents/Resources/Fonts")


def load_fonts() -> None:
    """Use SF Mono when the system has it (it ships inside Terminal.app)."""
    global _mono_family
    for weight in ("Regular", "Medium", "Bold"):
        f = _SF_MONO_DIR / f"SF-Mono-{weight}.otf"
        if f.exists():
            fid = QFontDatabase.addApplicationFont(str(f))
            if fid >= 0 and QFontDatabase.applicationFontFamilies(fid):
                _mono_family = QFontDatabase.applicationFontFamilies(fid)[0]


def mono(size: float, weight: QFont.Weight = QFont.Normal) -> QFont:
    f = QFont(_mono_family)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def ui(size: float, weight: QFont.Weight = QFont.Normal, spacing: float = 0.0) -> QFont:
    f = QFont()
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def alpha(c: QColor, a: float) -> QColor:
    c = QColor(c)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


def card(p: QPainter, rect: QRectF, radius: float = 14, fill: QColor | None = None) -> None:
    """A flat card with a hairline border and a faint shadow under it."""
    fill = fill or SURFACE
    p.setPen(Qt.NoPen)
    p.setBrush(SHADOW)
    p.drawRoundedRect(rect.adjusted(0, 2, 0, 0), radius, radius)
    p.setPen(QPen(BORDER, 1))
    p.setBrush(fill)
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -1.5), radius, radius)


def keycap(p: QPainter, rect: QRectF, radius: float, face: QColor | None = None,
           edge: QColor | None = None, depth: float = 2.0) -> QRectF:
    """A matte keycap: the face sits on a slightly darker edge. Returns the face rect."""
    face, edge = face or KEY, edge or KEY_EDGE
    p.setPen(Qt.NoPen)
    p.setBrush(edge)
    p.drawRoundedRect(rect, radius, radius)
    face_rect = rect.adjusted(0, 0, 0, -depth)
    p.setPen(QPen(alpha(edge, 0.7), 1))
    p.setBrush(face)
    p.drawRoundedRect(face_rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    return face_rect


_grain: QImage | None = None


def grain() -> QImage:
    """A small tile of paper grain, drawn once and tiled over the background."""
    global _grain
    if _grain is None:
        size = 160
        img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        rng = random.Random(7)
        p = QPainter(img)
        for _ in range(2600):
            shade = rng.choice((0, 255))
            p.setPen(QColor(shade, shade, shade, rng.randint(6, 16)))
            p.drawPoint(rng.randrange(size), rng.randrange(size))
        p.end()
        _grain = img
    return _grain


def stylesheet() -> str:
    return f"""
QWidget {{ background: transparent; color: {TEXT.name()}; }}
QMainWindow {{ background: {BG.name()}; }}
QToolTip {{
    background: {TEXT.name()}; color: {SURFACE.name()};
    border: none; border-radius: 6px; padding: 6px 8px;
}}
QDialog, QMessageBox, QInputDialog {{ background: {SURFACE.name()}; }}
QDialog QLabel {{ color: {TEXT.name()}; }}
QPlainTextEdit, QTextEdit {{
    background: {KEY.name()}; border: 1px solid {BORDER.name()};
    border-radius: 8px; padding: 8px; selection-background-color: {ACCENT_SOFT.name()};
    selection-color: {TEXT.name()};
}}
QPushButton {{
    background: {KEY.name()}; border: 1px solid {BORDER.name()};
    border-bottom: 2px solid {KEY_EDGE.name()}; border-radius: 7px; padding: 5px 14px;
}}
QPushButton:hover {{ border-color: {MUTED.name()}; }}
QPushButton:default {{ background: {TEXT.name()}; color: {SURFACE.name()}; border-color: {TEXT.name()}; }}
QLabel {{ background: transparent; }}
QMenu {{
    background: {SURFACE.name()}; border: 1px solid {BORDER.name()}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 5px 22px 5px 22px; border-radius: 5px; color: {TEXT.name()}; }}
QMenu::item:selected {{ background: {ACCENT_SOFT.name()}; }}
QMenu::separator {{ height: 1px; background: {BORDER.name()}; margin: 4px 8px; }}
QLabel#muted {{ color: {MUTED.name()}; font-size: 12px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {BORDER.name()}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
