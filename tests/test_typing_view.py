import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from fastype.engine import TypingSession
from fastype.ui.typing_view import TypingView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("lines", [2, 3, 4, 5])
def test_next_row_stays_visible(app, lines):
    view = TypingView()
    view.resize(700, 400)
    view.set_session(TypingSession(" ".join(["practice makes perfect"] * 60)), lines)
    view.resize(700, view.maximumHeight())
    assert view.visible_lines == lines  # the wanted lines really fit
    s = view.session
    while not s.finished:
        s.type_char(s.target[s.position])
        line = view._caret_line()
        if line + 1 < len(view._lines):
            assert line - view._first_line() <= view.visible_lines - 2
