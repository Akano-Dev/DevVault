"""Section header row: small caps title, completion count, collapse arrow."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ..core import painting
from ..core.theme import C, M, font, px
from ..models.entities import Section


class SectionHeader(QWidget):
    collapse_toggled = Signal(int)
    menu_requested = Signal(int, QPoint)
    edit_requested = Signal(int)

    def __init__(self, section: Section, compact: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.section = section
        self.compact = compact
        self._swallow_release = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.section.id, self.mapToGlobal(pos))
        )
        self._apply_font()
        self._apply_height()

    def _apply_font(self) -> None:
        self.setFont(font(M.SECTION_SIZE_COMPACT if self.compact else M.SECTION_SIZE))

    def _apply_height(self) -> None:
        # Slack so ascenders are not clipped by drawText's rectangle.
        fm = self.fontMetrics()
        line = max(fm.height(), fm.tightBoundingRect("ÀCgjpq").height()) + px(3)
        self.setFixedHeight(line + px(0 if self.compact else 2))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(px(140), self.height())

    def set_section(self, section: Section, compact: bool) -> None:
        self.section = section
        if compact != self.compact:
            self.compact = compact
            self._apply_font()
            self._apply_height()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)
        hovered = self.underMouse()

        x = px(M.GAP_SMALL)

        # The collapse arrow only appears on hover -- the reference shows a
        # plain yellow heading with no chrome.
        if hovered or self.section.collapsed:
            ay = self.height() // 2
            u = max(1, px(2))
            color = C.YELLOW if hovered else C.YELLOW_DIM
            if self.section.collapsed:
                for i in range(3):
                    p.fillRect(
                        QRect(x + i * u, ay - (3 - i) * u // 2, u, max(u, (3 - i) * u)), color
                    )
            else:
                for i in range(3):
                    p.fillRect(QRect(x + i * u, ay - u, u, u * (1 if i != 1 else 2)), color)
            x += u * 4

        title = self.section.title
        fm = p.fontMetrics()

        # The count sits where the checkbox column is, so only show it when the
        # row is hovered -- otherwise it would clash with the boxes below.
        count_w = 0
        if hovered:
            count = f"{self.section.done_count}/{self.section.total_count}"
            count_w = fm.horizontalAdvance(count) + px(M.GAP)
            painting.draw_text(
                p,
                QRect(self.width() - count_w, 0, count_w - px(M.CHECK_MARGIN), self.height()),
                count,
                C.YELLOW_DIM,
                self.font(),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            )

        text_rect = QRect(x, 0, max(0, self.width() - x - count_w), self.height())
        painting.draw_text(
            p,
            text_rect,
            fm.elidedText(title, Qt.TextElideMode.ElideRight, text_rect.width()),
            C.SECTION,
            self.font(),
        )
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Accept the press so it cannot reach the window-drag handler.

        Otherwise it bubbles to the drag area, startSystemMove() runs, and the
        native move loop eats the release that would toggle the section.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._swallow_release:
            self._swallow_release = False
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.collapse_toggled.emit(self.section.id)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """See TaskRow: undo the first release's collapse, then rename."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._swallow_release = True
        self.collapse_toggled.emit(self.section.id)
        self.edit_requested.emit(self.section.id)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)
