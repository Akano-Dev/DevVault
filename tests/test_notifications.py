"""Notification service tests.

Run with: python -m pytest tests -q

The tray is stubbed throughout: QSystemTrayIcon.showMessage hands the toast to
the OS, which cannot be asserted on and would pop real toasts on the desktop
while the suite runs.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.database.db import Database  # noqa: E402
from app.services.notifications import NotificationService  # noqa: E402
from app.services.settings import DEFAULTS, SettingsStore  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeTray(QObject):
    """Stands in for TrayController: records messages, never touches the OS."""

    message_clicked = Signal()

    def __init__(self, supported: bool = True, explode: bool = False) -> None:
        super().__init__()
        self.supported = supported
        self.explode = explode
        self.messages: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> bool:
        if self.explode:
            raise RuntimeError("the tray went away mid-notification")
        self.messages.append((title, message))
        return self.supported


@pytest.fixture()
def service(qapp, tmp_path: Path):
    db = Database(tmp_path / "notify.db")
    settings = SettingsStore(db)
    tray = FakeTray()
    yield NotificationService(tray, settings), tray, settings
    db.close()


# ----------------------------------------------------------------------
def test_notifications_are_on_by_default():
    assert DEFAULTS["notifications_enabled"] is True


def test_notify_sends_when_enabled(service):
    svc, tray, _ = service
    assert svc.notify("Title", "Body") is True
    assert tray.messages == [("Title", "Body")]


def test_the_setting_switches_the_whole_channel_off(service):
    svc, tray, settings = service
    settings.set("notifications_enabled", False)
    assert svc.notify("Title", "Body") is False
    assert tray.messages == []


def test_warn_ignores_the_setting(service):
    """A failure the user must know about outlives their toast preference."""
    svc, tray, settings = service
    settings.set("notifications_enabled", False)
    assert svc.warn("hotkey unavailable", "Ctrl+Shift+Q is taken") is True
    assert tray.messages == [("hotkey unavailable", "Ctrl+Shift+Q is taken")]


def test_an_unsupported_platform_reports_false_not_a_crash(qapp, tmp_path: Path):
    db = Database(tmp_path / "unsupported.db")
    tray = FakeTray(supported=False)
    svc = NotificationService(tray, SettingsStore(db))
    assert svc.notify("Title", "Body") is False
    db.close()


def test_a_throwing_tray_never_reaches_the_caller(qapp, tmp_path: Path):
    """The event being announced already happened; the announcement is extra."""
    db = Database(tmp_path / "explode.db")
    tray = FakeTray(explode=True)
    svc = NotificationService(tray, SettingsStore(db))
    assert svc.notify("Title", "Body") is False
    db.close()


def test_a_clicked_toast_reaches_the_app(service):
    svc, tray, _ = service
    seen: list[bool] = []
    svc.activated.connect(lambda: seen.append(True))
    tray.message_clicked.emit()
    assert seen == [True]


# ----------------------------------------------------------------------
# Wording
# ----------------------------------------------------------------------
def test_timer_message_names_the_task_and_the_goal(service):
    svc, tray, _ = service
    svc.timer_target_reached("Coding (Learning)", 21 * 3600)
    title, body = tray.messages[0]
    assert "Coding (Learning)" in title
    assert "21h" in body


def test_a_goalless_stopwatch_does_not_claim_a_target(service):
    svc, tray, _ = service
    svc.timer_target_reached("Reading", 0)
    _, body = tray.messages[0]
    assert "-" not in body      # format_compact renders 0 as "-"


def test_objective_message_quotes_the_title(service):
    svc, tray, _ = service
    svc.objective_complete("Weekly Challenge")
    title, body = tray.messages[0]
    assert title == "Objective complete!"
    assert "Weekly Challenge" in body


def test_an_untitled_objective_still_reads_as_a_sentence(service):
    svc, tray, _ = service
    svc.objective_complete("")
    assert tray.messages[0][1] == "Every task is done."
