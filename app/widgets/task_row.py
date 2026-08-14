"""One task line: pixel checkbox, optional icon, text, priority pip."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ..core import painting
from ..core.icons import draw_glyph
from ..core.theme import C, M, PRIORITY_COLORS, font, px
from ..models.entities import Task


class TaskRow(QWidget):
    toggled = Signal(int)            # task id
    edit_requested = Signal(int)
    menu_requested = Signal(int, QPoint)

    def __init__(
        self,
        task: Task,
        show_icons: bool = True,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.task = task
        self.show_icons = show_icons
        self.compact = compact
        self._anim_value = 1.0 if task.done else 0.0
        self._anim: QVariantAnimation | None = None
        self._hover_box = False
        self._swallow_release = False
        self._enter = 1.0                       # 1.0 = fully settled
        self._enter_anim: QVariantAnimation | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.task.id, self.mapToGlobal(pos))
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._apply_font()
        self._update_height()

    def _apply_font(self) -> None:
        self.setFont(font(M.TASK_SIZE_COMPACT if self.compact else M.TASK_SIZE))

    # ------------------------------------------------------------------
    def _update_height(self) -> None:
        h = px(M.ROW_HEIGHT_COMPACT if self.compact else M.ROW_HEIGHT)
        # Never let the design metric clip the chosen font.
        fm = self.fontMetrics()
        line = max(fm.height(), fm.tightBoundingRect("ÀCgjpq").height()) + px(3)
        self.setFixedHeight(max(h, line))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(px(160), self.height())

    def set_task(self, task: Task, show_icons: bool, compact: bool) -> None:
        state_changed = task.done != self.task.done
        self.task = task
        self.show_icons = show_icons
        if compact != self.compact:
            self.compact = compact
            self._apply_font()
            self._update_height()
        if state_changed:
            self._animate_to(1.0 if task.done else 0.0)
        else:
            self._anim_value = 1.0 if task.done else 0.0
            self.update()

    def _animate_to(self, target: float) -> None:
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(140)
        anim.setStartValue(float(self._anim_value))
        anim.setEndValue(float(target))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_anim)
        anim.start()
        self._anim = anim

    def _on_anim(self, value) -> None:
        self._anim_value = float(value)
        self.update()

    # ------------------------------------------------------------------
    def _box_size(self) -> int:
        return px(M.CHECK_SIZE if not self.compact else M.CHECK_SIZE - 2)

    def _box_rect(self) -> QRect:
        """The reference right-aligns the checkboxes into a single column."""
        box = self._box_size()
        return QRect(
            self.width() - box - px(M.CHECK_MARGIN),
            (self.height() - box) // 2,
            box,
            box,
        )

    def start_entrance(self, delay_ms: int) -> None:
        """Slide-and-fade the row in, staggered behind the rows above it."""
        self._enter = 0.0
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(190)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_enter)
        QTimer.singleShot(delay_ms, anim.start)
        self._enter_anim = anim

    def _on_enter(self, value: float) -> None:
        self._enter = float(value)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)

        if self._enter < 1.0:
            # Fade up and slide in from the left by a few pixels.
            p.setOpacity(max(0.0, self._enter))
            p.translate(int((1.0 - self._enter) * px(10)), 0)

        if self.underMouse():
            p.fillRect(self.rect(), C.HOVER)
        if self.hasFocus():
            p.fillRect(QRect(0, 0, px(2), self.height()), C.YELLOW)

        x = px(M.GAP_SMALL)

        if self.show_icons:
            size = px(M.ICON_SIZE if not self.compact else M.ICON_SIZE - 3)
            icon_rect = QRect(x, (self.height() - size) // 2, size, size)
            # Icons keep their own colours, exactly as in the reference.
            if self.task.icon and draw_glyph(p, icon_rect, self.task.icon):
                x = icon_rect.right() + px(M.ICON_GAP)
            else:
                x += size + px(M.ICON_GAP)   # keep the text column aligned

        box = self._box_rect()
        pip = px(3)
        right_edge = box.left() - px(M.GAP)
        if self.task.priority > 0:
            right_edge -= pip + px(M.GAP_SMALL)

        # Completed text is NOT dimmed or struck through in the reference.
        text_rect = QRect(x, 0, max(0, right_edge - x), self.height())
        elided = QFontMetrics(self.font()).elidedText(
            self.task.text, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painting.draw_text(p, text_rect, elided, C.TASK, self.font())

        if self.task.priority > 0:
            color = PRIORITY_COLORS.get(self.task.priority, C.MUTED)
            p.fillRect(
                QRect(box.left() - px(M.GAP) - pip, (self.height() - pip * 3) // 2,
                      pip, pip * 3),
                color,
            )

        painting.draw_reference_checkbox(
            p, box, self.task.done, self._hover_box, self._anim_value
        )
        p.end()

    # ------------------------------------------------------------------
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

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        inside = self._box_rect().adjusted(-px(2), -px(2), px(2), px(2)).contains(
            event.position().toPoint()
        )
        if inside != self._hover_box:
            self._hover_box = inside
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_box = False
        self.update()
        super().leaveEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._swallow_release:
            # Release that closes a double-click -- it must not re-toggle.
            self._swallow_release = False
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.toggled.emit(self.task.id)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """Qt delivers press, release, double-click, release.

        The first release has already toggled the task, so undo that, mark the
        trailing release to be ignored, and open the editor instead.
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._swallow_release = True
        self.toggled.emit(self.task.id)
        self.edit_requested.emit(self.task.id)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggled.emit(self.task.id)
            return
        if event.key() == Qt.Key.Key_F2:
            self.edit_requested.emit(self.task.id)
            return
        super().keyPressEvent(event)
