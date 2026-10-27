"""Where the app's preferences live.

Normally the standard macOS preferences file. Set FASTYPE_SETTINGS to an .ini path to
use a separate file instead (tests and scripted runs do this so they don't touch yours).
"""
import os

from PySide6.QtCore import QSettings


def settings() -> QSettings:
    if path := os.environ.get("FASTYPE_SETTINGS"):
        return QSettings(path, QSettings.IniFormat)
    return QSettings("Fastype", "Fastype")
