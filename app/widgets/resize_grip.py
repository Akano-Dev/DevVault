"""A visible corner handle for resizing the frameless overlay.

The window edges are draggable, but a 6px transparent ring is not something
anyone discovers on their own. This puts an obvious pixel-art grip in the
bottom-right corner and drives a native resize from it.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ..core.theme import C, px


class ResizeGrip(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Drag to resize")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._start_geom: QRect | None = None
        self._start_pos: QPoint | None = None

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        color = C.YELLOW if self.underMouse() else C.MUTED
        unit = max(1, px(2))
        # Three stepped diagonal pips, like a classic corner gripper.
        for row in range(3):
            for col in range(3 - row):
                x = self.width() - (col + 1) * (unit * 2)
                y = self.height() - (row + 1) * (unit * 2)
                p.fillRect(x, y, unit, unit, color)
        p.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        window = self.window()
        handle = window.windowHandle() if window else None
        if handle is not None and handle.startSystemResize(Qt.Edge.RightEdge
                                                          | Qt.Edge.BottomEdge):
            event.accept()
            return
        # Fallback for platforms without native resize (and for tests).
        self._start_geom = QRect(window.geometry())
        self._start_pos = event.globalPosition().toPoint()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start_geom is None or self._start_pos is None:
            return super().mouseMoveEvent(event)
        window = self.window()
        delta = event.globalPosition().toPoint() - self._start_pos
        width = max(window.minimumWidth(), self._start_geom.width() + delta.x())
        height = max(window.minimumHeight(), self._start_geom.height() + delta.y())
        window.resize(width, height)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._start_geom = None
        self._start_pos = None
        super().mouseReleaseEvent(event)
