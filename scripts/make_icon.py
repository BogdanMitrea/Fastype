"""Draws the app icon in code and writes assets/Fastype.icns plus the in-app PNG.

Run with the project's venv: .venv/bin/python scripts/make_icon.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parent.parent
PAPER, PAPER_DARK = QColor("#efece6"), QColor("#e2ded6")
INK, INK_EDGE = QColor("#23211e"), QColor("#0d0c0b")
ORANGE = QColor("#d9622b")


def rounded(rect: QRectF, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, r, r)
    return path


def draw(size: int = 1024) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 1024, size / 1024)

    # macOS icon grid: an 824px rounded square centred on the 1024 canvas, with a soft drop shadow.
    tile = QRectF(100, 100, 824, 824)
    for k in range(6):
        p.fillPath(rounded(tile.adjusted(-k, 8 - k, k, 10 + k), 185 + k), QColor(40, 30, 20, 10))
    bg = QLinearGradient(tile.topLeft(), tile.bottomLeft())
    bg.setColorAt(0, PAPER)
    bg.setColorAt(1, PAPER_DARK)
    p.fillPath(rounded(tile, 185), bg)

    # An ink keycap sitting on its darker edge, like the logo in the app.
    cap = QRectF(272, 250, 480, 500)
    p.fillPath(rounded(cap.adjusted(0, 18, 0, 22), 96), QColor(40, 30, 20, 40))  # shadow on the tile
    p.fillPath(rounded(cap, 96), INK_EDGE)
    face = cap.adjusted(0, 0, 0, -44)
    p.fillPath(rounded(face, 96), INK)
    top = QRectF(face.left() + 46, face.top() + 30, face.width() - 92, face.height() - 80)
    p.fillPath(rounded(top, 70), QColor("#2c2a26"))  # the slightly dished top of the cap

    caret = QRectF(top.center().x() - 24, top.top() + 70, 48, top.height() - 140)
    p.fillPath(rounded(caret, 24), ORANGE)
    p.end()
    return img


def main() -> None:
    QGuiApplication(sys.argv)
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    big = draw(1024)
    big.save(str(ROOT / "src" / "fastype" / "assets" / "icon.png"))
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Fastype.iconset"
        iconset.mkdir()
        for s in (16, 32, 128, 256, 512):
            draw(s).save(str(iconset / f"icon_{s}x{s}.png"))
            draw(s * 2).save(str(iconset / f"icon_{s}x{s}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(assets / "Fastype.icns")],
                       check=True)
    print("wrote assets/Fastype.icns and src/fastype/assets/icon.png")


if __name__ == "__main__":
    main()
