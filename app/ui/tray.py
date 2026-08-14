"""System tray icon and menu."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..core.icons import app_icon


class TrayController(QObject):
    toggle_requested = Signal()
    new_objective_requested = Signal()
    settings_requested = Signal()
    always_on_top_toggled = Signal(bool)
    exit_requested = Signal()

    def __init__(self, always_on_top: bool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.icon.setToolTip("QuestPanel")

        menu = QMenu()
        header = menu.addAction("QuestPanel")
        header.setEnabled(False)
        menu.addSeparator()

        self.action_toggle = menu.addAction("Show / Hide")
        self.action_toggle.triggered.connect(self.toggle_requested.emit)

        self.action_new = menu.addAction("New Objective")
        self.action_new.triggered.connect(self.new_objective_requested.emit)

        self.action_settings = menu.addAction("Settings")
        self.action_settings.triggered.connect(self.settings_requested.emit)

        self.action_on_top = menu.addAction("Always on Top")
        self.action_on_top.setCheckable(True)
        self.action_on_top.setChecked(always_on_top)
        self.action_on_top.toggled.connect(self.always_on_top_toggled.emit)

        menu.addSeparator()
        self.action_exit = menu.addAction("Exit")
        self.action_exit.triggered.connect(self.exit_requested.emit)

        self._menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.toggle_requested.emit()

    def set_visible_state(self, visible: bool) -> None:
        self.action_toggle.setText("Hide" if visible else "Show")

    def set_always_on_top(self, enabled: bool) -> None:
        self.action_on_top.blockSignals(True)
        self.action_on_top.setChecked(enabled)
        self.action_on_top.blockSignals(False)

    def notify(self, title: str, message: str) -> None:
        if QSystemTrayIcon.supportsMessages():
            self.icon.showMessage(title, message, app_icon(), 3000)
