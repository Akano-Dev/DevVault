"""Mediates between the quest panel view, the repository and the dialogs.

Keeping this out of ``application.py`` lets the bootstrap stay small: this
class owns every CRUD interaction and context menu the panel offers.
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtWidgets import QDialog, QMenu

from ..core.theme import M, PRIORITY_NAMES, font
from ..database.repo import Repo
from ..models.entities import Section, Task
from ..services.settings import SettingsStore
from ..utils.duration import format_compact
from ..widgets.pixel_controls import MENU_STYLE
from ..widgets.quest_panel import QuestPanelView
from .dialogs import TaskDialog, TextDialog, TimerDialog, confirm


class PanelController(QObject):
    settings_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()
    always_on_top_requested = Signal(bool)
    task_completed = Signal(bool)      # True when checked, False when unchecked
    objective_completed = Signal(int)
    ui_interaction = Signal()          # for the optional UI click sound
    sound_requested = Signal(str)      # sfx key, played by the audio service
    timer_target_reached = Signal(str, int)   # task text, target seconds

    def __init__(
        self,
        panel: QuestPanelView,
        repo: Repo,
        settings: SettingsStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.panel = panel
        self.repo = repo
        self.settings = settings
        self.timers = panel.timers
        self.timers.target_reached.connect(self._on_target_reached)

        panel.task_timer_toggled.connect(self.toggle_timer)
        panel.task_toggled.connect(self.toggle_task)
        panel.task_edit_requested.connect(self.edit_task)
        panel.task_add_requested.connect(self.add_task)
        panel.task_menu_requested.connect(self.show_task_menu)
        panel.section_menu_requested.connect(self.show_section_menu)
        panel.section_edit_requested.connect(self.rename_section)
        panel.section_add_requested.connect(self.add_section)
        panel.objective_edit_requested.connect(self.edit_objective)
        panel.objective_menu_requested.connect(self.show_objective_menu)
        panel.objective_completed.connect(self.objective_completed.emit)
        panel.settings_requested.connect(self.settings_requested.emit)
        panel.hide_requested.connect(self.hide_requested.emit)
        panel.quit_requested.connect(self.quit_requested.emit)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def _find_task(self, task_id: int) -> Task | None:
        if self.panel.objective is None:
            return None
        for section in self.panel.objective.sections:
            for task in section.tasks:
                if task.id == task_id:
                    return task
        return None

    def _find_section(self, section_id: int) -> Section | None:
        if self.panel.objective is None:
            return None
        for section in self.panel.objective.sections:
            if section.id == section_id:
                return section
        return None

    def _dialog_parent(self):
        return self.panel.window()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def toggle_task(self, task_id: int) -> None:
        done = self.repo.toggle_task(task_id)
        # Finishing a task stops its clock: leaving it running would keep
        # billing time to work the user has just declared finished.
        if done and self.timers.is_running(task_id):
            self.timers.pause(task_id)
        self.panel.apply_task_state(task_id, done)
        self.task_completed.emit(done)

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------
    def toggle_timer(self, task_id: int) -> None:
        task = self._find_task(task_id)
        if task is None:
            return
        if not task.timer_enabled:
            self.configure_timer(task_id)
            return
        running = self.timers.toggle(task_id, task.timer_elapsed, task.timer_target)
        self.sound_requested.emit("timer_start" if running else "timer_pause")

    def configure_timer(self, task_id: int) -> None:
        """Add, retarget or remove the timer on an existing task."""
        task = self._find_task(task_id)
        if task is None:
            return
        dialog = TimerDialog(
            task.text, task.timer_enabled, task.timer_target, task.timer_elapsed,
            self._dialog_parent(),
        )
        dialog.adjustSize()
        dialog.center_on(self._dialog_parent())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        enabled, target = dialog.values()
        if not enabled and self.timers.is_running(task_id):
            self.timers.pause(task_id)
        self.repo.set_task_timer(task_id, enabled, target)
        if dialog.reset_requested():
            self.timers.reset(task_id)
        self.panel.reload()

    def reset_timer(self, task_id: int) -> None:
        task = self._find_task(task_id)
        if task is None:
            return
        if task.timer_elapsed and not confirm(
            self._dialog_parent(), "Reset Timer",
            f'Clear the {format_compact(task.timer_elapsed)} tracked on "{task.text}"?',
            ok_text="Reset",
        ):
            return
        self.timers.reset(task_id)
        self.panel.reload()

    def _on_target_reached(self, task_id: int) -> None:
        self.sound_requested.emit("timer_done")
        # The panel is often hidden or behind something when a long timer
        # finishes -- which is exactly when the desktop toast is the only way
        # the news reaches you.
        task = self._find_task(task_id)
        if task is not None:
            self.timer_target_reached.emit(task.text, task.timer_target)

    def edit_task(self, task_id: int) -> None:
        task = self._find_task(task_id)
        if task is None:
            return
        dialog = TaskDialog("Edit Task", task.text, task.priority, task.icon,
                            task.timer_enabled, task.timer_target,
                            self._dialog_parent())
        dialog.adjustSize()
        dialog.center_on(self._dialog_parent())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, priority, icon, timer_enabled, timer_target = dialog.values()
        if not text:
            return
        if not timer_enabled and self.timers.is_running(task_id):
            self.timers.pause(task_id)
        self.repo.update_task(task_id, text, priority, icon, timer_enabled, timer_target)
        self.panel.reload()

    def add_task(self, section_id: int) -> None:
        dialog = TaskDialog("New Task", parent=self._dialog_parent())
        dialog.adjustSize()
        dialog.center_on(self._dialog_parent())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, priority, icon, timer_enabled, timer_target = dialog.values()
        if not text:
            return
        self.repo.create_task(section_id, text, priority, icon, timer_enabled, timer_target)
        self.sound_requested.emit("task_add")
        self.panel.reload()

    def delete_task(self, task_id: int) -> None:
        task = self._find_task(task_id)
        if task is None:
            return
        if not confirm(self._dialog_parent(), "Delete Task", f'Delete "{task.text}"?'):
            return
        # Drop the clock first: a pending flush would otherwise write an
        # elapsed total back to a row that no longer exists.
        self.timers.forget(task_id)
        self.repo.delete_task(task_id)
        self.sound_requested.emit("task_delete")
        self.panel.reload()

    def _forget_timers_for(self, tasks: Iterable[Task]) -> None:
        """Drop the clocks on rows that are about to be deleted.

        A running timer banks its total on a 15s cycle. If the row is gone by
        then the write lands on nothing and the clock keeps ticking against a
        task that no longer exists, so it has to be dropped up front -- the
        same reason :meth:`delete_task` calls ``forget`` before deleting.
        """
        for task in tasks:
            self.timers.forget(task.id)

    def set_task_priority(self, task_id: int, priority: int) -> None:
        task = self._find_task(task_id)
        if task is None:
            return
        self.repo.update_task(task_id, task.text, priority, task.icon)
        self.panel.reload()

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def add_section(self) -> None:
        if self.panel.objective is None:
            return
        dialog = TextDialog("New Section", "Name", "", parent=self._dialog_parent())
        dialog.adjustSize()
        dialog.center_on(self._dialog_parent())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.value():
            return
        self.repo.create_section(self.panel.objective.id, dialog.value())
        self.panel.reload()

    def rename_section(self, section_id: int) -> None:
        section = self._find_section(section_id)
        if section is None:
            return
        dialog = TextDialog("Rename Section", "Name", section.title,
                            parent=self._dialog_parent())
        dialog.adjustSize()
        dialog.center_on(self._dialog_parent())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.value():
            return
        self.repo.rename_section(section_id, dialog.value())
        self.panel.reload()

    def delete_section(self, section_id: int) -> None:
        section = self._find_section(section_id)
        if section is None:
            return
        message = f'Delete "{section.title}" and its {section.total_count} task(s)?'
        if not confirm(self._dialog_parent(), "Delete Section", message):
            return
        self._forget_timers_for(section.tasks)
        self.repo.delete_section(section_id)
        self.panel.reload()

    # ------------------------------------------------------------------
    # Objectives
    # ------------------------------------------------------------------
    def new_objective(self) -> None:
        dialog = TextDialog(
            "New Objective", "Title", "", "Subtitle (optional)", "",
            parent=self._dialog_parent(),
        )
        dialog.adjustSize()
        dialog.center_on(self._dialog_parent())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.value():
            return
        objective_id = self.repo.create_objective(dialog.value(), dialog.second_value())
        # A fresh objective needs somewhere to put tasks.
        self.repo.create_section(objective_id, "Tasks")
        self.panel.reload()

    def edit_objective(self) -> None:
        objective = self.panel.objective
        if objective is None:
            return
        dialog = TextDialog(
            "Edit Objective", "Title", objective.title,
            "Subtitle (optional)", objective.subtitle,
            parent=self._dialog_parent(),
        )
        dialog.adjustSize()
        dialog.center_on(self._dialog_parent())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.value():
            return
        self.repo.update_objective(objective.id, dialog.value(), dialog.second_value())
        self.panel.reload()

    def delete_objective(self) -> None:
        objective = self.panel.objective
        if objective is None:
            return
        if not confirm(
            self._dialog_parent(), "Delete Objective",
            f'Delete "{objective.title}" and all of its sections and tasks?',
        ):
            return
        self._forget_timers_for(objective.tasks)
        self.repo.delete_objective(objective.id)
        self.panel.reload()

    def switch_objective(self, objective_id: int) -> None:
        # Bank any running clock first: its row is about to leave the panel,
        # and time that keeps accruing where you cannot see it is time you
        # cannot trust.
        self.timers.pause_all()
        self.repo.set_active_objective(objective_id)
        self.settings.set("active_objective_id", objective_id)
        self.panel.reload()

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------
    def _menu(self) -> QMenu:
        self.ui_interaction.emit()
        menu = QMenu(self.panel)
        menu.setStyleSheet(MENU_STYLE)
        menu.setFont(font(M.TASK_SIZE))
        return menu

    def show_task_menu(self, task_id: int, global_pos: QPoint) -> None:
        task = self._find_task(task_id)
        if task is None or self.panel.objective is None:
            return
        menu = self._menu()
        menu.addAction(
            "Mark Incomplete" if task.done else "Mark Complete",
            lambda: self.toggle_task(task_id),
        )
        menu.addAction("Edit Task\tF2", lambda: self.edit_task(task_id))

        menu.addSeparator()
        if task.timer_enabled:
            running = self.timers.is_running(task_id)
            menu.addAction(
                "Pause Timer\tT" if running else "Start Timer\tT",
                lambda: self.toggle_timer(task_id),
            )
            elapsed = self.timers.elapsed(task_id, task.timer_elapsed)
            spent = menu.addAction(
                f"Tracked: {format_compact(elapsed)}"
                + (f" / {format_compact(task.timer_target)}" if task.timer_target else "")
            )
            spent.setEnabled(False)
            menu.addAction("Reset Timer", lambda: self.reset_timer(task_id))
            menu.addAction("Timer Settings", lambda: self.configure_timer(task_id))
        else:
            menu.addAction("Add Timer", lambda: self.configure_timer(task_id))

        menu.addSeparator()
        priority_menu = menu.addMenu("Priority")
        for value, name in PRIORITY_NAMES.items():
            action = priority_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(task.priority == value)
            action.triggered.connect(
                lambda _checked=False, v=value: self.set_task_priority(task_id, v)
            )

        menu.addSeparator()
        menu.addAction("Move Up", lambda: self._reorder_task(task_id, -1))
        menu.addAction("Move Down", lambda: self._reorder_task(task_id, 1))

        others = [s for s in self.panel.objective.sections if s.id != task.section_id]
        if others:
            move_menu = menu.addMenu("Move to Section")
            for section in others:
                move_menu.addAction(
                    section.title,
                    lambda _checked=False, sid=section.id: self._move_task(task_id, sid),
                )

        menu.addSeparator()
        menu.addAction("Delete Task", lambda: self.delete_task(task_id))
        menu.exec(global_pos)

    def _reorder_task(self, task_id: int, delta: int) -> None:
        self.repo.reorder_task(task_id, delta)
        self.panel.reload()

    def _move_task(self, task_id: int, section_id: int) -> None:
        self.repo.move_task_to_section(task_id, section_id)
        self.panel.reload()

    def show_section_menu(self, section_id: int, global_pos: QPoint) -> None:
        section = self._find_section(section_id)
        if section is None:
            return
        menu = self._menu()
        menu.addAction("Add Task", lambda: self.add_task(section_id))
        menu.addAction("Rename Section", lambda: self.rename_section(section_id))
        menu.addSeparator()
        menu.addAction("Move Up", lambda: self._reorder_section(section_id, -1))
        menu.addAction("Move Down", lambda: self._reorder_section(section_id, 1))
        menu.addAction(
            "Expand" if section.collapsed else "Collapse",
            lambda: self._set_collapsed(section_id, not section.collapsed),
        )
        menu.addSeparator()
        menu.addAction("Delete Section", lambda: self.delete_section(section_id))
        menu.exec(global_pos)

    def _reorder_section(self, section_id: int, delta: int) -> None:
        self.repo.reorder_section(section_id, delta)
        self.panel.reload()

    def _set_collapsed(self, section_id: int, collapsed: bool) -> None:
        self.repo.set_section_collapsed(section_id, collapsed)
        self.panel.reload()

    def show_objective_menu(self, global_pos: QPoint) -> None:
        objective = self.panel.objective
        menu = self._menu()

        if objective is not None:
            menu.addAction("Edit Objective", self.edit_objective)
            menu.addAction("Add Section", self.add_section)
            if objective.sections:
                add_menu = menu.addMenu("Add Task to")
                for section in objective.sections:
                    add_menu.addAction(
                        section.title,
                        lambda _checked=False, sid=section.id: self.add_task(sid),
                    )
            menu.addSeparator()

        objectives = self.repo.list_objectives()
        if len(objectives) > 1 and objective is not None:
            switch_menu = menu.addMenu("Switch Objective")
            for item in objectives:
                action = switch_menu.addAction(item.title)
                action.setCheckable(True)
                action.setChecked(item.id == objective.id)
                action.triggered.connect(
                    lambda _checked=False, oid=item.id: self.switch_objective(oid)
                )

        menu.addAction("New Objective", self.new_objective)
        if objective is not None:
            menu.addAction("Delete Objective", self.delete_objective)
            menu.addSeparator()
            menu.addAction("Clear Completed Tasks", self._clear_completed)
            menu.addAction("Reset All Tasks", self._reset_objective)

        menu.addSeparator()
        on_top = menu.addAction("Always on Top")
        on_top.setCheckable(True)
        on_top.setChecked(self.settings.bool("always_on_top"))
        on_top.toggled.connect(self.always_on_top_requested.emit)

        menu.addAction("Settings", self.settings_requested.emit)
        menu.addAction("Hide Panel", self.hide_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit QuestPanel", self.quit_requested.emit)
        menu.exec(global_pos)

    def _clear_completed(self) -> None:
        if self.panel.objective is None:
            return
        self._forget_timers_for(t for t in self.panel.objective.tasks if t.done)
        removed = self.repo.clear_completed(self.panel.objective.id)
        if removed:
            self.panel.reload()

    def _reset_objective(self) -> None:
        objective = self.panel.objective
        if objective is None:
            return
        if not confirm(
            self._dialog_parent(), "Reset Objective",
            f'Mark all {objective.total_count} task(s) in "{objective.title}" incomplete?',
            ok_text="Reset", danger=False,
        ):
            return
        self.repo.reset_objective(objective.id)
        self.panel.reload()
