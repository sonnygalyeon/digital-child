import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="Install the desktop extra to exercise the Qt window")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from digital_child.desktop_app import DesktopWindow, MessageCard  # noqa: E402
from digital_child.storage import SQLiteRepository  # noqa: E402


def wait_for(predicate, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("Desktop condition timed out")


def test_window_sends_unicode_restores_history_and_closes_core(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DIGITAL_CHILD_LLM_PROVIDER", "disabled")
    monkeypatch.setenv("DIGITAL_CHILD_RESEARCH_PROVIDER", "disabled")
    app = QApplication.instance() or QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    database = tmp_path / "window.db"
    window = DesktopWindow(database, auto_research=False)
    window.show()
    try:
        wait_for(lambda: window.ready)
        assert window.orb.isVisible()
        window.input.setPlainText("Привет! <b>Текст</b> & память")
        window.input.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(window.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        assert window.input.toPlainText().endswith("\n")
        QTest.keyClick(window.input, Qt.Key.Key_Return)
        assert window.busy
        assert window.orb.state.process == "thinking"
        assert not window.send_button.isEnabled()
        wait_for(lambda: not window.busy)
        cards = window.findChildren(MessageCard)
        assert len(cards) == 2
        assert cards[0].body.text() == "Привет! <b>Текст</b> & память"
        assert cards[0].body.textFormat() == Qt.TextFormat.PlainText
        assert cards[1].text
        assert window.orb.state.process == "idle"
        window.pause_button.click()
        wait_for(lambda: not window.busy and window.loop_paused)
        assert window.pause_button.text() == "Продолжить"
        assert window.grab().save(str(tmp_path / "window.png"))
    finally:
        process = window.process
        window.close()
        wait_for(lambda: not window.isVisible(), timeout=6)
        assert process is not None and not process.is_alive()

    with SQLiteRepository(database) as repository:
        assert len(repository.recent_conversation("local-user")) == 2

    reopened = DesktopWindow(database, auto_research=False)
    reopened.show()
    try:
        wait_for(lambda: reopened.ready)
        cards = reopened.findChildren(MessageCard)
        assert len(cards) == 2
        assert cards[0].body.text() == "Привет! <b>Текст</b> & память"
    finally:
        reopened.close()
        wait_for(lambda: not reopened.isVisible(), timeout=6)
        app.processEvents()
