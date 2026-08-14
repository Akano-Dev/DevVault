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
from ..widgets.pixel_controls import PixelButton, style_combo, style_line_edit


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
    """Task text plus priority and optional icon."""

    def __init__(
        self,
        title: str,
        text: str = "",
        priority: int = 0,
        icon: str = "",
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

        self.add_buttons()
        self.setMinimumWidth(px(250))
        self.edit.setFocus()

    def values(self) -> tuple[str, int, str]:
        return (
            self.edit.text().strip(),
            int(self.priority.currentData()),
            str(self.icon.currentData() or ""),
        )


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
