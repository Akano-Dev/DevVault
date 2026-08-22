"""Notification tests: the policy layer and the pixel toast it draws.

Run with: python -m pytest tests -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, Qt, Signal  # noqa: E402
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import theme  # noqa: E402
from app.database.db import Database  # noqa: E402
from app.services.notifications import NotificationService  # noqa: E402
from app.services.settings import DEFAULTS, SettingsStore  # noqa: E402
from app.widgets import toast as toast_mod  # noqa: E402
from app.widgets.toast import PixelToast, ToastStack, _wrap  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    return app


class FakeTray(QObject):
    """Stands in for TrayController: records balloons, never touches the OS."""

    message_clicked = Signal()

    def __init__(self, supported: bool = True) -> None:
        super().__init__()
        self.supported = supported
        self.messages: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> bool:
        self.messages.append((title, message))
        return self.supported


@pytest.fixture()
def service(qapp, tmp_path: Path):
    db = Database(tmp_path / "notify.db")
    settings = SettingsStore(db)
    tray = FakeTray()
    svc = NotificationService(tray, settings)
    yield svc, tray, settings
    svc.clear()
    db.close()


def sounds_from(svc: NotificationService) -> list[str]:
    played: list[str] = []
    svc.sound_requested.connect(played.append)
    return played


def release_at(toast: PixelToast, point: QPoint) -> None:
    toast.mouseReleaseEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


# ----------------------------------------------------------------------
# Policy
# ----------------------------------------------------------------------
def test_notifications_are_on_by_default():
    assert DEFAULTS["notifications_enabled"] is True


def test_notify_puts_a_toast_on_screen(service):
    svc, tray, _ = service
    assert svc.notify("Title", "Body") is True
    assert svc.stack.count == 1
    shown = svc.stack.toasts[0]
    assert (shown.title, shown.body) == ("Title", "Body")
    # The pixel toast replaces the native balloon; the tray is untouched.
    assert tray.messages == []


def test_the_setting_switches_the_whole_channel_off(service):
    svc, _, settings = service
    settings.set("notifications_enabled", False)
    assert svc.notify("Title", "Body") is False
    assert svc.stack.count == 0


def test_warn_ignores_the_setting(service):
    """A failure the user must know about outlives their toast preference."""
    svc, _, settings = service
    settings.set("notifications_enabled", False)
    assert svc.warn("hotkey unavailable", "Ctrl+Shift+Q is taken") is True
    assert svc.stack.toasts[0].title == "hotkey unavailable"


def test_a_clicked_toast_reaches_the_app(service):
    svc, _, _ = service
    seen: list[bool] = []
    svc.activated.connect(lambda: seen.append(True))
    svc.notify("Title", "Body")
    svc.stack.toasts[0].activated.emit()
    assert seen == [True]


def test_falls_back_to_the_tray_when_there_is_no_screen(service, monkeypatch):
    """Headless or mid-display-change: the news still has to get out."""
    svc, tray, _ = service
    monkeypatch.setattr(
        toast_mod.QGuiApplication, "primaryScreen", staticmethod(lambda: None)
    )
    assert svc.notify("Title", "Body") is True
    assert svc.stack.count == 0
    assert tray.messages == [("Title", "Body")]


# ----------------------------------------------------------------------
# Sound
# ----------------------------------------------------------------------
def test_a_plain_notification_plays_the_chime(service):
    svc, _, _ = service
    played = sounds_from(svc)
    svc.notify("Title", "Body")
    assert played == ["notify"]


def test_events_that_already_sounded_ask_for_silence(service):
    """The timer alarm and the completion fanfare are the sound for those
    events; adding the toast chime on top makes one event sound twice."""
    svc, _, _ = service
    played = sounds_from(svc)
    svc.timer_target_reached("Coding (Learning)", 21 * 3600)
    svc.objective_complete("Weekly Challenge")
    assert played == []


def test_a_suppressed_notification_makes_no_sound(service):
    svc, _, settings = service
    played = sounds_from(svc)
    settings.set("notifications_enabled", False)
    svc.notify("Title", "Body")
    assert played == []


# ----------------------------------------------------------------------
# Wording
# ----------------------------------------------------------------------
def test_timer_message_names_the_task_and_the_goal(service):
    """The task name belongs in the body: the title is one line and elides."""
    svc, _, _ = service
    svc.timer_target_reached("Coding (Learning)", 21 * 3600)
    shown = svc.stack.toasts[0]
    assert shown.title == "Time's up!"
    assert "Coding (Learning)" in shown.body
    assert "21h" in shown.body
    assert shown.icon == "clock"


def test_a_goalless_stopwatch_does_not_claim_a_target(service):
    svc, _, _ = service
    svc.timer_target_reached("Reading", 0)
    body = svc.stack.toasts[0].body
    # format_compact renders 0 as "-", which must never reach the toast as a goal.
    assert "- reached" not in body
    assert body == "Reading - time tracked."


def test_objective_message_quotes_the_title(service):
    svc, _, _ = service
    svc.objective_complete("Weekly Challenge")
    shown = svc.stack.toasts[0]
    assert shown.title == "Objective complete!"
    assert "Weekly Challenge" in shown.body


def test_an_untitled_objective_still_reads_as_a_sentence(service):
    svc, _, _ = service
    svc.objective_complete("")
    assert svc.stack.toasts[0].body == "Every task is done."


# ----------------------------------------------------------------------
# The toast itself
# ----------------------------------------------------------------------
def test_toasts_park_in_the_top_right_corner(qapp):
    stack = ToastStack()
    stack.show("One", "Body")
    area = QGuiApplication.primaryScreen().availableGeometry()
    toast = stack.toasts[0]

    assert toast._parked.y() >= area.top()
    assert toast._parked.x() + toast.width() <= area.right() + 1
    # Hugging the right edge, not floating in the middle of the screen.
    assert area.right() - (toast._parked.x() + toast.width()) < theme.px(40)
    stack.clear()


def test_toasts_stack_downward_newest_lowest(qapp):
    stack = ToastStack()
    stack.show("First", "Body")
    stack.show("Second", "Body")
    first, second = stack.toasts
    assert second._parked.y() > first._parked.y()
    assert second._parked.x() == first._parked.x()
    stack.clear()


def test_the_corner_holds_a_bounded_number_of_toasts(qapp):
    stack = ToastStack(max_visible=2)
    for i in range(5):
        stack.show(f"Toast {i}", "Body")
    assert stack.count <= 2
    stack.clear()


def test_a_toast_never_takes_focus(qapp):
    """One arriving mid-sentence must not eat the next keystroke."""
    toast = PixelToast("Title", "Body")
    flags = toast.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    toast.deleteLater()


def test_hovering_holds_the_toast_open(qapp):
    toast = PixelToast("Title", "Body", lifetime_ms=2000)
    before = toast._remaining
    toast._hovered = True
    for _ in range(10):
        toast._on_tick()
    assert toast._remaining == before      # the countdown is paused

    toast._hovered = False
    toast._on_tick()
    assert toast._remaining < before
    toast.deleteLater()


def test_the_countdown_dismisses_the_toast(qapp):
    toast = PixelToast("Title", "Body", lifetime_ms=1200)
    toast._remaining = 0
    toast._on_tick()
    assert toast._closing is True
    toast.deleteLater()


def test_clicking_the_cross_dismisses_without_activating(qapp):
    toast = PixelToast("Title", "Body")
    activated: list[bool] = []
    toast.activated.connect(lambda: activated.append(True))
    release_at(toast, toast._close_rect().center())
    assert activated == []
    assert toast._closing is True
    toast.deleteLater()


def test_clicking_the_body_activates(qapp):
    toast = PixelToast("Title", "Body")
    activated: list[bool] = []
    toast.activated.connect(lambda: activated.append(True))
    release_at(toast, QPoint(30, toast.height() // 2))
    assert activated == [True]
    toast.deleteLater()


# ----------------------------------------------------------------------
# Word wrap
# ----------------------------------------------------------------------
def test_wrap_keeps_short_text_on_one_line(qapp):
    fm = QFontMetrics(QFont(theme.family(), 12))
    assert _wrap(fm, "Short", 400, 2) == ["Short"]


def test_wrap_breaks_onto_a_second_line(qapp):
    fm = QFontMetrics(QFont(theme.family(), 12))
    text = "Ctrl+Shift+Q is already claimed by another application"
    lines = _wrap(fm, text, fm.horizontalAdvance("Ctrl+Shift+Q is"), 2)
    assert len(lines) == 2


def test_wrap_never_exceeds_the_line_budget(qapp):
    fm = QFontMetrics(QFont(theme.family(), 12))
    text = " ".join(["word"] * 60)
    assert len(_wrap(fm, text, 80, 2)) == 2


def test_wrap_handles_empty_text(qapp):
    fm = QFontMetrics(QFont(theme.family(), 12))
    assert _wrap(fm, "", 100, 2) == []
