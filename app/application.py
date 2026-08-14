"""Application controller: owns the singletons and wires the components."""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .core import theme
from .core.hotkey import HotkeyError, HotkeyManager
from .core.icons import app_icon
from .core.single_instance import SingleInstance
from .database.db import Database
from .database.repo import Repo
from .services.audio import AudioService
from .services.settings import SettingsStore
from .ui.overlay import OverlayWindow
from .ui.panel_controller import PanelController
from .ui.settings_window import SettingsWindow
from .ui.tray import TrayController
from .widgets.quest_panel import QuestPanelView


class QuestPanelApp(QObject):
    def __init__(
        self, qapp: QApplication, single_instance: SingleInstance | None = None
    ) -> None:
        super().__init__()
        self.qapp = qapp
        self._quitting = False

        self.db = Database()
        self.settings = SettingsStore(self.db)
        self.repo = Repo(self.db)
        self.repo.seed_if_empty()

        theme.set_scale(self.settings.float("ui_scale"))
        theme.load_fonts()

        # Overlay + panel ------------------------------------------------
        self.overlay = OverlayWindow(self.settings)
        self.panel = QuestPanelView(self.repo, self.settings)
        self.overlay.set_content(self.panel)
        self.overlay.close_requested.connect(self.quit)

        self.panel_controller = PanelController(self.panel, self.repo, self.settings, self)
        self.panel_controller.settings_requested.connect(self.open_settings)
        self.panel_controller.hide_requested.connect(self.overlay.hide_overlay)
        # The 'x' on the panel exits the app outright, matching what a close
        # button reads as. Hiding lives on Esc, the hotkey and the tray.
        self.panel_controller.quit_requested.connect(self.quit)
        self.panel_controller.always_on_top_requested.connect(self.set_always_on_top)
        self.panel_controller.task_completed.connect(self.on_task_completed)
        self.panel_controller.objective_completed.connect(self.on_objective_completed)
        self.panel_controller.ui_interaction.connect(lambda: self.audio.play("ui_click"))
        # Bound through a lambda, not self.audio.play: the audio service does
        # not exist yet at this point in construction.
        self.panel_controller.sound_requested.connect(lambda key: self.audio.play(key))
        self.panel.reload()
        self.overlay.apply_effects()

        # Audio ----------------------------------------------------------
        self.audio = AudioService(self.settings, self)
        self.audio.start_music()
        self.settings_window: SettingsWindow | None = None

        # Tray -----------------------------------------------------------
        self.tray = TrayController(self.settings.bool("always_on_top"), self)
        self.tray.toggle_requested.connect(self.toggle)
        self.tray.settings_requested.connect(self.open_settings)
        self.tray.new_objective_requested.connect(self.new_objective)
        self.tray.always_on_top_toggled.connect(self.set_always_on_top)
        self.tray.exit_requested.connect(self.quit)
        self.overlay.visibility_changed.connect(self.tray.set_visible_state)

        # A second launch raises this window instead of stacking another one.
        self.single_instance = single_instance
        if single_instance is not None:
            single_instance.activated.connect(self.raise_overlay)

        # Global hotkey --------------------------------------------------
        self.hotkey = HotkeyManager(self)
        self.hotkey.install(qapp)
        self.hotkey.activated.connect(self.toggle)
        self.register_hotkey(self.settings.str("hotkey"), announce=False)

        if self.settings.bool("visible_on_start"):
            self.overlay.show_overlay(animate=True)
        self.tray.set_visible_state(self.overlay.isVisible())

    # ------------------------------------------------------------------
    def register_hotkey(self, sequence: str, announce: bool = True) -> bool:
        try:
            self.hotkey.register(sequence)
        except HotkeyError as exc:
            if announce:
                self.tray.notify("QuestPanel - hotkey unavailable", str(exc))
            else:
                print(f"[QuestPanel] hotkey: {exc}", file=sys.stderr)
            return False
        self.settings.set("hotkey", sequence)
        return True

    def toggle(self) -> None:
        self.overlay.toggle_overlay()

    def raise_overlay(self) -> None:
        """Bring the panel forward -- used when a second launch is blocked."""
        if not self.overlay.isVisible():
            self.overlay.show_overlay()
        else:
            self.overlay.raise_()
        self.tray.set_visible_state(True)

    def set_always_on_top(self, enabled: bool) -> None:
        self.overlay.set_always_on_top(enabled)
        self.tray.set_always_on_top(enabled)

    def on_task_completed(self, done: bool) -> None:
        self.audio.play("task_complete" if done else "task_uncomplete")

    def on_objective_completed(self, objective_id: int) -> None:
        self.audio.play("objective_complete")
        self.panel.celebrate()

    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        if self.settings_window is None:
            window = SettingsWindow(self.settings, self.overlay)
            window.appearance_changed.connect(self.apply_appearance)
            window.audio_changed.connect(self.audio.apply_settings)
            window.always_on_top_changed.connect(self.set_always_on_top)
            window.hotkey_changed.connect(self.on_hotkey_changed)
            window.closed.connect(self._on_settings_closed)
            self.settings_window = window
        # Pick up any files dropped into the music folder since it was last open.
        self.settings_window._refresh_tracks()
        self.settings_window.show_near(self.overlay)

    def _on_settings_closed(self) -> None:
        self.settings_window = None

    def on_hotkey_changed(self, sequence: str) -> None:
        previous = self.settings.str("hotkey")
        ok = self.register_hotkey(sequence, announce=False)
        if self.settings_window is not None:
            self.settings_window.report_hotkey_result(
                ok, f"Active: {sequence}" if ok else f"Taken - keeping {previous}"
            )
        if not ok:
            self.register_hotkey(previous, announce=False)

    def apply_appearance(self) -> None:
        theme.set_scale(self.settings.float("ui_scale"))
        self.overlay.apply_opacity()
        self.overlay.refresh_metrics()
        self.overlay.apply_effects()
        self.panel.apply_settings()

    def new_objective(self) -> None:
        if not self.overlay.isVisible():
            self.overlay.show_overlay()
        self.panel_controller.new_objective()

    def quit(self) -> None:
        """Shut everything down. Safe to call more than once.

        Closing the overlay emits close_requested, which lands back here, so
        without this guard the second pass hit an already-closed database and
        the exception aborted the rest of the teardown -- leaving the tray icon
        behind.
        """
        if self._quitting:
            return
        self._quitting = True
        self.qapp.setProperty("quitting", True)
        self.overlay.save_geometry()
        self.hotkey.unregister()
        self.audio.shutdown()
        if self.settings_window is not None:
            self.settings_window.close()
        self.tray.icon.hide()
        self.db.close()
        self.qapp.quit()


def run() -> int:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("QuestPanel")
    qapp.setOrganizationName("QuestPanel")
    qapp.setWindowIcon(app_icon())
    # The overlay lives in the tray; closing the last window must not exit.
    qapp.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None, "QuestPanel",
            "No system tray was found. QuestPanel will run without tray integration.",
        )

    guard = SingleInstance()
    if not guard.try_acquire():
        # Another copy is already running; it has been asked to show itself.
        print("[QuestPanel] already running - raised the existing window.")
        return 0

    controller = QuestPanelApp(qapp, guard)
    qapp._questpanel_controller = controller  # type: ignore[attr-defined]
    try:
        return qapp.exec()
    finally:
        guard.release()
