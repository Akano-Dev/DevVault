"""Desktop notifications, drawn by QuestPanel in its own pixel language.

The policy follows the reference pomodoro app (Refference/pomodoro-main):
prefer a real desktop notification over an in-panel banner, keep the whole
channel behind one setting, make clicking one bring the app back, and treat
every notification as best-effort -- the thing it announces has already
happened and matters more than the announcement.

Where that app hands the toast to Electron (and so to Windows), this one
paints its own: a Windows 11 toast is a rounded system-font card branded with
the host process's name, which for a dev run reads "Python". The pixel toast
in widgets/toast.py belongs to the app instead, appears in the top-right
corner, and comes with its own chiptune.

The native tray balloon stays as a fallback for the case where no screen is
available to park a window on.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..utils.duration import format_compact
from ..widgets.toast import ToastStack
from .settings import SettingsStore


class NotificationService(QObject):
    """Policy layer over the pixel toast stack."""

    activated = Signal()             # the user clicked a notification
    sound_requested = Signal(str)    # sfx key, played by the audio service

    def __init__(
        self,
        tray,
        settings: SettingsStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.tray = tray
        self.settings = settings
        self.stack = ToastStack()

    @property
    def enabled(self) -> bool:
        return self.settings.bool("notifications_enabled")

    # ------------------------------------------------------------------
    def notify(
        self,
        title: str,
        body: str,
        icon: str = "quest",
        silent: bool = False,
    ) -> bool:
        """Show one notification. Returns whether it actually went out.

        ``silent`` is for events that already made their own noise -- a
        finished timer plays its alarm, and stacking the notification chime on
        top of it just makes the same event sound twice.
        """
        if not self.enabled:
            return False
        return self._send(title, body, icon, silent)

    def warn(self, title: str, body: str, icon: str = "gear") -> bool:
        """Show a notification that ignores the setting.

        Reserved for the app reporting that it could not do something the user
        asked for -- a hotkey it failed to claim, say. Silently swallowing that
        because notifications are off would leave the app looking broken with
        no explanation anywhere.
        """
        return self._send(title, body, icon, silent=False)

    def _send(self, title: str, body: str, icon: str, silent: bool) -> bool:
        try:
            toast = self.stack.show(
                title, body, icon, on_activated=self.activated.emit
            )
        except Exception:
            toast = None
        if toast is not None:
            if not silent:
                self.sound_requested.emit("notify")
            return True
        # No screen to park a window on: fall back to the tray balloon rather
        # than dropping the news entirely.
        try:
            return bool(self.tray.notify(title, body))
        except Exception:
            # Best-effort by design: see the module docstring.
            return False

    # ------------------------------------------------------------------
    # The events themselves, phrased in one place so the wording stays
    # consistent wherever they are fired from.
    # ------------------------------------------------------------------
    def timer_target_reached(self, task_text: str, target_seconds: int) -> bool:
        goal = format_compact(target_seconds) if target_seconds else ""
        # The task name goes in the body, not the title: the body gets two
        # lines, and a long task name in the title elides after a word or two.
        body = f"{task_text} - {goal} reached." if goal else f"{task_text} - time tracked."
        # Silent: the timer already sounded its own alarm.
        return self.notify("Time's up!", body, "clock", silent=True)

    def objective_complete(self, title: str) -> bool:
        return self.notify(
            "Objective complete!",
            f'"{title}" is fully checked off.' if title else "Every task is done.",
            "star",
            silent=True,          # the completion fanfare covers this one
        )

    def clear(self) -> None:
        """Drop every toast on screen -- used on shutdown."""
        self.stack.clear()
