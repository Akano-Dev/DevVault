"""The quest panel: a data-driven view of the active objective."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core import painting
from ..core.theme import C, M, font, px
from ..database.repo import Repo
from ..models.entities import Objective, Section, Task
from ..services.settings import SettingsStore
from ..services.timers import TimerService
from ..utils.dragging import try_start_drag
from .add_row import AddRow
from .celebration import CelebrationOverlay
from .objective_card import ObjectiveCard
from .pixel_controls import PixelProgress
from .section_header import SectionHeader
from .task_row import TaskRow


class _DragArea(QWidget):
    """Background container whose empty space moves the window."""

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not try_start_drag(self, event):
            super().mousePressEvent(event)


class _BodyCard(QWidget):
    """The lower card. Paints the reference's inset card behind the rows."""

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not try_start_drag(self, event):
            super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.draw_card(p, self.rect(), C.PANEL, C.CARD_BORDER_SOFT)
        p.end()


class QuestPanelView(QWidget):
    """Renders the active objective and relays user intent to the controller."""

    task_toggled = Signal(int)
    task_edit_requested = Signal(int)
    task_add_requested = Signal(int)          # section id
    task_menu_requested = Signal(int, QPoint)
    task_timer_toggled = Signal(int)          # task id -- start/pause its clock
    section_menu_requested = Signal(int, QPoint)
    section_edit_requested = Signal(int)
    section_add_requested = Signal()
    objective_edit_requested = Signal()
    objective_menu_requested = Signal(QPoint)
    objective_completed = Signal(int)
    settings_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()

    def __init__(
        self,
        repo: Repo,
        settings: SettingsStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.settings = settings
        self.objective: Objective | None = None
        self._entrance_index = 0
        self._task_rows: dict[int, TaskRow] = {}
        self._section_headers: dict[int, SectionHeader] = {}
        self._was_complete = False

        # The clocks outlive any individual row: rebuilding the list must not
        # stop a timer that is running.
        self.timers = TimerService(repo, self)
        self.timers.tick.connect(self._on_timer_tick)
        self.timers.state_changed.connect(self._on_timer_state)

        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Root holds the two cards; the gaps between them show the desktop.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = ObjectiveCard(self.settings.bool("compact_mode"), self)
        self.header.edit_requested.connect(self.objective_edit_requested.emit)
        self.header.menu_requested.connect(self.objective_menu_requested.emit)
        self.header.settings_requested.connect(self.settings_requested.emit)
        self.header.quit_requested.connect(self.quit_requested.emit)
        self.header.add_requested.connect(self._on_header_add)
        root.addWidget(self.header)

        # Body card, inset on both sides exactly as in the reference.
        body_row = QHBoxLayout()
        body_row.setContentsMargins(px(M.BODY_INSET_LEFT), px(M.CARD_GAP),
                                    px(M.BODY_INSET_RIGHT), 0)
        body_row.setSpacing(0)

        self.body_card = _BodyCard(self)
        card_layout = QVBoxLayout(self.body_card)
        card_layout.setContentsMargins(
            px(M.BODY_PAD_X), px(M.BODY_PAD_TOP), px(M.BODY_PAD_X), px(M.BODY_PAD_BOTTOM)
        )
        card_layout.setSpacing(0)
        body_row.addWidget(self.body_card)
        root.addLayout(body_row, 1)

        self.scroll = QScrollArea(self.body_card)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setStyleSheet(
            f"""
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: {px(5)}px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C.SEPARATOR.lighter(140).name()}; min-height: {px(14)}px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C.YELLOW_DIM.name()}; }}
            QScrollBar::add-line, QScrollBar::sub-line,
            QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
            """
        )

        # Let the list shrink so the whole overlay can be made small; without
        # this the layout's own minimum sets the floor instead of MIN_H.
        self.scroll.setMinimumHeight(px(20))

        self.body = _DragArea()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        self.body_layout.addStretch(1)
        self.scroll.setWidget(self.body)
        card_layout.addWidget(self.scroll, 1)

        # Footer -- the reference has no progress meter, so this is kept
        # deliberately quiet and can be switched off in Settings.
        self.footer = QWidget(self.body_card)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(0, px(M.GAP), px(M.CHECK_MARGIN), 0)
        footer_layout.setSpacing(px(M.GAP))

        self.progress = PixelProgress(self.footer)
        self.progress_value = QLabel("0%", self.footer)
        self.progress_value.setFont(font(M.SECTION_SIZE))
        self.progress_value.setMinimumWidth(px(30))
        self.progress_value.setStyleSheet(f"color: {C.YELLOW.name()}; background: transparent;")
        self.progress_value.setAlignment(Qt.AlignmentFlag.AlignRight
                                         | Qt.AlignmentFlag.AlignVCenter)
        footer_layout.addWidget(self.progress, 1)
        footer_layout.addWidget(self.progress_value)
        card_layout.addWidget(self.footer)

        self.celebration = CelebrationOverlay(self)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    def reload(self) -> None:
        """Re-read the active objective from the database and rebuild rows."""
        self.objective = self.repo.active_objective()
        self._rebuild()

    def _clear_body(self) -> None:
        self._task_rows.clear()
        self._section_headers.clear()
        while self.body_layout.count() > 1:
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild(self) -> None:
        compact = self.settings.bool("compact_mode")
        show_icons = self.settings.bool("show_icons")
        animate = self.settings.bool("animations_enabled")
        self._entrance_index = 0

        self._clear_body()
        self.header.set_objective(self.objective, compact, animate)

        if self.objective is not None:
            for index, section in enumerate(self.objective.sections):
                self._add_section(section, index, compact, show_icons, animate)
        else:
            empty = QLabel("Right-click for a new objective", self.body)
            empty.setFont(font(M.TASK_SIZE))
            empty.setStyleSheet(f"color: {C.MUTED.name()}; background: transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.body_layout.insertWidget(self.body_layout.count() - 1, empty)

        self._apply_visibility_settings()
        self.update_progress(animate=False)
        self._was_complete = bool(self.objective and self.objective.is_complete)

    def _add_section(
        self, section: Section, index: int, compact: bool, show_icons: bool,
        animate: bool = False,
    ) -> None:
        insert_at = self.body_layout.count() - 1
        if index > 0:
            spacer = QWidget(self.body)
            spacer.setFixedHeight(px(M.GAP if not compact else M.GAP_SMALL))
            self.body_layout.insertWidget(insert_at, spacer)
            insert_at += 1

        head = SectionHeader(section, compact, self.body)
        head.collapse_toggled.connect(self._on_collapse)
        head.menu_requested.connect(self.section_menu_requested.emit)
        head.edit_requested.connect(self.section_edit_requested.emit)
        self._section_headers[section.id] = head
        self.body_layout.insertWidget(insert_at, head)
        insert_at += 1

        if section.collapsed:
            return
        for task in section.tasks:
            row = TaskRow(task, show_icons, compact, self.body)
            row.toggled.connect(self.task_toggled.emit)
            row.edit_requested.connect(self.task_edit_requested.emit)
            row.menu_requested.connect(self.task_menu_requested.emit)
            row.timer_toggled.connect(self.task_timer_toggled.emit)
            # A rebuilt row starts blank; hand it back whatever its clock is
            # actually at right now.
            row.set_timer_state(
                self.timers.elapsed(task.id, task.timer_elapsed),
                self.timers.is_running(task.id),
            )
            self._task_rows[task.id] = row
            self.body_layout.insertWidget(insert_at, row)
            if animate:
                # Cap the stagger: with many rows the tail would crawl in.
                row.start_entrance(min(self._entrance_index * 22, 260))
                self._entrance_index += 1
            insert_at += 1

        add = AddRow(section.id, "Add task", compact, self.body)
        add.clicked.connect(self.task_add_requested.emit)
        self.body_layout.insertWidget(insert_at, add)

    def _on_header_add(self) -> None:
        """The header '+' adds to the last section, or makes one if there is none."""
        if self.objective is None or not self.objective.sections:
            self.section_add_requested.emit()
            return
        self.task_add_requested.emit(self.objective.sections[-1].id)

    def _on_collapse(self, section_id: int) -> None:
        if self.objective is None:
            return
        for section in self.objective.sections:
            if section.id == section_id:
                self.repo.set_section_collapsed(section_id, not section.collapsed)
                break
        self.reload()

    # ------------------------------------------------------------------
    # Incremental updates
    # ------------------------------------------------------------------
    def apply_task_state(self, task_id: int, done: bool) -> None:
        """Update one row in place so the checkbox animation can play."""
        if self.objective is None:
            return
        task: Task | None = None
        section: Section | None = None
        for sec in self.objective.sections:
            for t in sec.tasks:
                if t.id == task_id:
                    task, section = t, sec
                    break
            if task is not None:
                break
        if task is None or section is None:
            return

        task.done = done
        row = self._task_rows.get(task_id)
        if row is not None:
            row.set_task(task, self.settings.bool("show_icons"),
                         self.settings.bool("compact_mode"))
        head = self._section_headers.get(section.id)
        if head is not None:
            head.set_section(section, self.settings.bool("compact_mode"))
        self.update_progress()

        complete = self.objective.is_complete
        if complete and not self._was_complete:
            self.objective_completed.emit(self.objective.id)
        self._was_complete = complete

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------
    def _on_timer_tick(self, task_id: int, elapsed: int) -> None:
        row = self._task_rows.get(task_id)
        if row is not None:
            row.set_timer_state(elapsed, self.timers.is_running(task_id))
        task = self._find_task(task_id)
        if task is not None:
            task.timer_elapsed = elapsed

    def _on_timer_state(self, task_id: int, running: bool) -> None:
        row = self._task_rows.get(task_id)
        if row is not None:
            row.set_timer_state(
                self.timers.elapsed(task_id, row.task.timer_elapsed), running
            )

    def _find_task(self, task_id: int) -> Task | None:
        if self.objective is None:
            return None
        for section in self.objective.sections:
            for task in section.tasks:
                if task.id == task_id:
                    return task
        return None

    def update_progress(self, animate: bool = True) -> None:
        value = self.objective.progress if self.objective else 0.0
        self.progress.setValue(value)
        if self.objective and self.objective.total_count:
            done, total = self.objective.done_count, self.objective.total_count
            self.progress_value.setText(f"{done}/{total}")
            color = C.GREEN if self.objective.is_complete else C.YELLOW
        else:
            self.progress_value.setText("0%")
            color = C.MUTED
        self.progress_value.setStyleSheet(f"color: {color.name()}; background: transparent;")

    def _apply_visibility_settings(self) -> None:
        show_progress = self.settings.bool("show_progress")
        self.footer.setVisible(show_progress)

    def apply_settings(self) -> None:
        """Re-read appearance settings and rebuild with the new metrics."""
        self.progress_value.setFont(font(M.SECTION_SIZE))
        card_layout: QVBoxLayout = self.body_card.layout()  # type: ignore[assignment]
        card_layout.setContentsMargins(
            px(M.BODY_PAD_X), px(M.BODY_PAD_TOP), px(M.BODY_PAD_X), px(M.BODY_PAD_BOTTOM)
        )
        self._rebuild()

    # ------------------------------------------------------------------
    def celebrate(self) -> None:
        title = self.objective.title if self.objective else ""
        self.celebration.play("OBJECTIVE COMPLETE", title or "Quest Completed!")

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.celebration.resize(self.size())
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not try_start_drag(self, event):
            super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.objective_menu_requested.emit(event.globalPos())
