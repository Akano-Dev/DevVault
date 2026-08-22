"""Native OS notifications for the events worth interrupting you for.

Modelled on the reference pomodoro app's system (Refference/pomodoro-main),
which is built on four rules:

* prefer the platform's own notification -- it survives the app being hidden,
  minimised or behind a fullscreen window, which an in-app banner does not;
* keep the whole channel behind one user setting, defaulting on;
* clicking the notification brings the app back to the front;
* a notification is best-effort. It must never raise into the caller, because
  the thing it is announcing (a finished timer, a completed objective) has
  already happened and matters more than the announcement.

Where that app calls Electron's ``Notification`` and falls back to the HTML5
API, this one calls the tray icon -- which is what Qt maps onto a real Windows
toast -- and reports failure to the caller instead.

One difference worth knowing: Electron lets the caller ask for a *silent*
toast, so the app's own chime is the only sound. Qt exposes no such flag, so
with both Sounds and Notifications enabled a finished timer makes two noises:
QuestPanel's chiptune and the system's default toast sound. Turning off either
setting resolves it.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..utils.duration import format_compact
from .settings import SettingsStore


class NotificationService(QObject):
    """Policy layer over the tray icon's message support."""

    activated = Signal()      # the user clicked a notification

    def __init__(
        self,
        tray,
        settings: SettingsStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.tray = tray
        self.settings = settings
        try:
            tray.message_clicked.connect(self.activated.emit)
        except AttributeError:
            pass          # a stand-in tray in the tests; clicking is optional

    @property
    def enabled(self) -> bool:
        return self.settings.bool("notifications_enabled")

    # ------------------------------------------------------------------
    def notify(self, title: str, body: str) -> bool:
        """Show one notification. Returns whether it actually went out."""
        if not self.enabled:
            return False
        return self._send(title, body)

    def warn(self, title: str, body: str) -> bool:
        """Show a notification that ignores the setting.

        Reserved for the app reporting that it could not do something the user
        asked for -- a hotkey it failed to claim, say. Silently swallowing that
        because notifications are off would leave the app looking broken with
        no explanation anywhere.
        """
        return self._send(title, body)

    def _send(self, title: str, body: str) -> bool:
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
        body = f"You've put {goal} into it." if goal else "Time tracked."
        return self.notify(f"{task_text} - time's up!", body)

    def objective_complete(self, title: str) -> bool:
        return self.notify(
            "Objective complete!",
            f'"{title}" is fully checked off.' if title else "Every task is done.",
        )
