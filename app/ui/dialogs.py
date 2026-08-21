"""Frameless pixel-styled dialogs used for every edit interaction."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..core import painting
from ..core.icons import ICON_NAMES, custom_icon_names, glyph_pixmap
from ..core.theme import C, M, PRIORITY_NAMES, font, label_font, px
from ..utils.duration import format_compact, parse_duration
from ..widgets.pixel_controls import (
    PixelButton,
    PixelCheckBox,
    style_combo,
    style_line_edit,
)

TIMER_HINT = "e.g. 21h, 90m, 1h 30m, 2:30 -- blank counts up"


class PixelDialog(QDialog):
    """Base dialog: frameless, beveled, draggable by its title strip."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._drag: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)

        outer = QVBoxLayout(self)
        b = px(M.BORDER) + px(1)
        outer.setContentsMargins(b + px(6), b + px(6), b + px(6), b + px(6))
        outer.setSpacing(px(M.GAP))

        self.title_label = QLabel(title.upper(), self)
        self.title_label.setFont(label_font(M.EYEBROW_SIZE))
        self.title_label.setStyleSheet(f"color: {C.EYEBROW.name()}; background: transparent;")
        outer.addWidget(self.title_label)

        self.form = QVBoxLayout()
        self.form.setSpacing(px(M.GAP_SMALL))
        outer.addLayout(self.form)
        outer.addStretch(1)

        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(px(M.GAP))
        self.buttons.addStretch(1)
        outer.addLayout(self.buttons)

        self._outer = outer

    # ------------------------------------------------------------------
    def add_field(self, label: str, widget: QWidget) -> QWidget:
        cap = QLabel(label.upper(), self)
        cap.setFont(label_font(M.SECTION_SIZE))
        cap.setStyleSheet(f"color: {C.SECTION.name()}; background: transparent;")
        self.form.addWidget(cap)
        widget.setFont(font(M.TASK_SIZE))
        self.form.addWidget(widget)
        return widget

    # ------------------------------------------------------------------
    # Timer fields -- shared by the task editor and the standalone dialog
    # ------------------------------------------------------------------
    def add_timer_fields(self, enabled: bool = False, target: int = 0) -> None:
        self.timer_check = PixelCheckBox("Track time on this task", self)
        self.timer_check.setFont(font(M.TASK_SIZE))
        self.timer_check.setChecked(bool(enabled))
        self.form.addWidget(self.timer_check)

        self.timer_target = style_line_edit(QLineEdit(self))
        self.timer_target.setPlaceholderText("no goal")
        if target:
            self.timer_target.setText(format_compact(target))
        self.add_field("Target", self.timer_target)

        self.timer_hint = QLabel(TIMER_HINT, self)
        self.timer_hint.setFont(font(M.SECTION_SIZE))
        self.timer_hint.setWordWrap(True)
        self.timer_hint.setStyleSheet(f"color: {C.MUTED.name()}; background: transparent;")
        self.form.addWidget(self.timer_hint)

        self.timer_check.toggled.connect(self._sync_timer_fields)
        self._sync_timer_fields(self.timer_check.isChecked())

    def _sync_timer_fields(self, enabled: bool) -> None:
        # The target only means anything with the timer on, so grey it out
        # rather than letting the user type into a field that is ignored.
        self.timer_target.setEnabled(enabled)
        self.timer_hint.setStyleSheet(
            f"color: {(C.MUTED if enabled else C.SEPARATOR).name()}; background: transparent;"
        )

    def timer_values(self) -> tuple[bool, int]:
        if not hasattr(self, "timer_check"):
            return False, 0
        if not self.timer_check.isChecked():
            return False, 0
        return True, parse_duration(self.timer_target.text())

    def timer_input_is_valid(self) -> bool:
        """Typed text that parses to nothing is a mistake, not 'no goal'."""
        if not hasattr(self, "timer_check") or not self.timer_check.isChecked():
            return True
        text = self.timer_target.text().strip()
        return not text or parse_duration(text) > 0

    def _reject_timer_input(self) -> None:
        self.timer_hint.setText(f"Could not read that duration. {TIMER_HINT}")
        self.timer_hint.setStyleSheet(f"color: {C.RED.name()}; background: transparent;")
        self.timer_target.setFocus()
        self.timer_target.selectAll()

    def accept(self) -> None:  # noqa: D102
        if not self.timer_input_is_valid():
            self._reject_timer_input()
            return
        super().accept()

    def add_buttons(self, ok_text: str = "Save", danger: bool = False) -> None:
        cancel = PixelButton("Cancel", self)
        cancel.setFont(font(M.TASK_SIZE))
        cancel.clicked.connect(self.reject)
        ok = PixelButton(ok_text, self, danger=danger)
        ok.setFont(font(M.TASK_SIZE))
        ok.clicked.connect(self.accept)
        self.buttons.addWidget(cancel)
        self.buttons.addWidget(ok)
        self._ok_button = ok

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)
        painting.draw_bevel_panel(p, self.rect(), thickness=px(M.BORDER))
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                return
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag = None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)

    def center_on(self, anchor: QWidget | None) -> None:
        if anchor is None or not anchor.isVisible():
            return
        geo = anchor.geometry()
        self.move(
            geo.center().x() - self.width() // 2,
            geo.center().y() - self.height() // 2,
        )


class TextDialog(PixelDialog):
    """Single-line text prompt (objective titles, section names)."""

    def __init__(
        self,
        title: str,
        label: str,
        initial: str = "",
        second_label: str | None = None,
        second_initial: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        self.edit = style_line_edit(QLineEdit(initial, self))
        self.add_field(label, self.edit)
        self.edit.selectAll()

        self.second: QLineEdit | None = None
        if second_label is not None:
            self.second = style_line_edit(QLineEdit(second_initial, self))
            self.add_field(second_label, self.second)

        self.add_buttons()
        self.setMinimumWidth(px(240))
        self.edit.setFocus()

    def value(self) -> str:
        return self.edit.text().strip()

    def second_value(self) -> str:
        return self.second.text().strip() if self.second else ""


class TaskDialog(PixelDialog):
    """Task text plus priority, optional icon and an optional timer."""

    def __init__(
        self,
        title: str,
        text: str = "",
        priority: int = 0,
        icon: str = "",
        timer_enabled: bool = False,
        timer_target: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)

        self.edit = style_line_edit(QLineEdit(text, self))
        self.add_field("Task", self.edit)
        self.edit.selectAll()

        self.priority = style_combo(QComboBox(self))
        for value, name in PRIORITY_NAMES.items():
            self.priority.addItem(name, value)
        self.priority.setCurrentIndex(max(0, min(3, priority)))
        self.add_field("Priority", self.priority)

        self.icon = style_combo(QComboBox(self))
        names = list(ICON_NAMES) + [
            n for n in custom_icon_names() if n not in ICON_NAMES
        ]
        for name in names:
            if name:
                self.icon.addItem(glyph_pixmap(name, px(12), C.SECTION), name.title(), name)
            else:
                self.icon.addItem("None", "")
        idx = self.icon.findData(icon)
        self.icon.setCurrentIndex(idx if idx >= 0 else 0)
        self.add_field("Icon", self.icon)

        self.add_timer_fields(timer_enabled, timer_target)

        self.add_buttons()
        self.setMinimumWidth(px(250))
        self.edit.setFocus()

    def values(self) -> tuple[str, int, str, bool, int]:
        enabled, target = self.timer_values()
        return (
            self.edit.text().strip(),
            int(self.priority.currentData()),
            str(self.icon.currentData() or ""),
            enabled,
            target,
        )


class TimerDialog(PixelDialog):
    """Add, retarget or clear the timer on a task that already exists."""

    def __init__(
        self,
        task_text: str,
        enabled: bool = False,
        target: int = 0,
        elapsed: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Task Timer", parent)

        name = QLabel(task_text, self)
        name.setWordWrap(True)
        name.setFont(font(M.TASK_SIZE))
        name.setStyleSheet(f"color: {C.TITLE.name()}; background: transparent;")
        self.form.addWidget(name)

        self.add_timer_fields(enabled, target)

        self.reset_check: PixelCheckBox | None = None
        if elapsed:
            tracked = QLabel(f"Tracked so far: {format_compact(elapsed)}", self)
            tracked.setFont(font(M.TASK_SIZE))
            tracked.setStyleSheet(f"color: {C.YELLOW.name()}; background: transparent;")
            self.form.addWidget(tracked)

            self.reset_check = PixelCheckBox("Clear tracked time", self)
            self.reset_check.setFont(font(M.TASK_SIZE))
            self.form.addWidget(self.reset_check)

        self.add_buttons()
        self.setMinimumWidth(px(250))
        self.timer_target.setFocus()

    def values(self) -> tuple[bool, int]:
        return self.timer_values()

    def reset_requested(self) -> bool:
        return self.reset_check is not None and self.reset_check.isChecked()


class ConfirmDialog(PixelDialog):
    def __init__(
        self,
        title: str,
        message: str,
        ok_text: str = "Delete",
        danger: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        label = QLabel(message, self)
        label.setWordWrap(True)
        label.setFont(font(M.TASK_SIZE))
        label.setStyleSheet(f"color: {C.TASK.name()}; background: transparent;")
        self.form.addWidget(label)
        self.add_buttons(ok_text, danger=danger)
        self.setMinimumWidth(px(230))


def confirm(
    parent: QWidget | None,
    title: str,
    message: str,
    ok_text: str = "Delete",
    danger: bool = True,
) -> bool:
    dialog = ConfirmDialog(title, message, ok_text, danger, parent)
    dialog.adjustSize()
    dialog.center_on(parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
