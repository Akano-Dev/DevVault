"""A dim '+ Add task' affordance at the end of each section.

The context menus cover every operation, but a right-click menu is not
discoverable -- this makes the common case visible.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ..core import painting
from ..core.icons import draw_glyph
from ..core.theme import C, M, font, px


class AddRow(QWidget):
    clicked = Signal(int)          # section id

    def __init__(
        self,
        section_id: int,
        label: str = "Add task",
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.section_id = section_id
        self.label = label
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(M.TASK_SIZE_COMPACT if compact else M.TASK_SIZE))
        fm = self.fontMetrics()
        self.setFixedHeight(max(px(M.ROW_HEIGHT_COMPACT), fm.height() + px(2)))
        self.setToolTip("Add a task to this section")

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(px(120), self.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)
        hovered = self.underMouse()
        if hovered:
            p.fillRect(self.rect(), C.HOVER)

        color = C.YELLOW if hovered else C.MUTED
        size = px(9)
        x = px(M.GAP_SMALL)
        glyph_rect = QRect(x, (self.height() - size) // 2, size, size)
        draw_glyph(p, glyph_rect, "ui_plus", color)

        x = glyph_rect.right() + px(M.GAP)
        painting.draw_text(
            p,
            QRect(x, 0, max(0, self.width() - x - px(M.GAP)), self.height()),
            self.label,
            color,
            self.font(),
        )
        p.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Accept the press so it cannot reach the window-drag handler.

        QWidget ignores presses by default, letting them bubble to the parent
        drag area, which calls startSystemMove(). That enters a native move
        loop on Windows and eats the release -- so the click never completes.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit(self.section_id)
        super().mouseReleaseEvent(event)
