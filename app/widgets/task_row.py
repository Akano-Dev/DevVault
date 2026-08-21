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
from ..core.theme import C, LABEL, M, PRIORITY_COLORS, font, px
from ..models.entities import Task
from ..utils.duration import format_clock, format_compact


class TaskRow(QWidget):
    toggled = Signal(int)            # task id
    edit_requested = Signal(int)
    menu_requested = Signal(int, QPoint)
    timer_toggled = Signal(int)      # chip clicked: start/pause this task's clock

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
        self._hover_chip = False
        self._swallow_release = False
        self._enter = 1.0                       # 1.0 = fully settled
        self._enter_anim: QVariantAnimation | None = None
        self._elapsed = int(task.timer_elapsed)  # live seconds, ticked by the service
        self._running = False

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
        self._update_timer_tooltip()

    def _apply_font(self) -> None:
        self.setFont(font(M.TASK_SIZE_COMPACT if self.compact else M.TASK_SIZE))

    # ------------------------------------------------------------------
    def _update_height(self) -> None:
        h = px(M.ROW_HEIGHT_COMPACT if self.compact else M.ROW_HEIGHT)
        # Never let the design metric clip the chosen font.
        fm = self.fontMetrics()
        line = max(fm.height(), fm.tightBoundingRect("ÀCgjpq").height()) + px(3)
        floor = max(h, line)
        if self.task.timer_enabled:
            # A row carrying a chip has to be tall enough for the whole slot,
            # bar included, or the meter silently drops off.
            timer_fm = QFontMetrics(self._timer_font())
            floor = max(floor, (
                timer_fm.tightBoundingRect("0123456789:").height()
                + px(3)
                + px(painting.TIMER_CHIP_FRAME) * 2
                + px(painting.TIMER_CHIP_BAR)
                + px(1)
            ))
        self.setFixedHeight(floor)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(px(160), self.height())

    def set_task(self, task: Task, show_icons: bool, compact: bool) -> None:
        state_changed = task.done != self.task.done
        self.task = task
        self.show_icons = show_icons
        if not self._running:
            self._elapsed = int(task.timer_elapsed)
        self._update_timer_tooltip()
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
    # Timer
    # ------------------------------------------------------------------
    def set_timer_state(self, elapsed: int, running: bool) -> None:
        """Called by the timer service on every tick and on start/pause."""
        if elapsed == self._elapsed and running == self._running:
            return
        self._elapsed = max(0, int(elapsed))
        self._running = bool(running)
        self._update_timer_tooltip()
        self.update()

    @property
    def timer_running(self) -> bool:
        return self._running

    def _timer_font(self):
        return font(
            M.TIMER_SIZE_COMPACT if self.compact else M.TIMER_SIZE, role=LABEL
        )

    def _timer_text(self) -> str:
        # The separators blank on alternate seconds while running -- the
        # cheapest possible "this clock is alive" signal.
        blink = self._running and self._elapsed % 2 == 1
        return format_clock(self._elapsed, blink_off=blink)

    def _chip_metrics(self) -> tuple[int, bool]:
        """Chip height and whether the durability bar fits inside it.

        Driven by the digits' own bounding box rather than a fixed metric:
        anything shorter and Qt centres the text on a half pixel, which is
        what turns a pixel font into a smear.
        """
        fm = QFontMetrics(self._timer_font())
        digits = fm.tightBoundingRect("0123456789:").height() + px(3)
        frame = px(painting.TIMER_CHIP_FRAME) * 2
        bar = px(painting.TIMER_CHIP_BAR)
        available = self.height() - px(1)

        if digits + frame + bar <= available:
            return digits + frame + bar, True
        return min(available, digits + frame), False

    def _chip_rect(self) -> QRect | None:
        """Where the timer chip sits, or None when this row has no timer."""
        if not self.task.timer_enabled:
            return None
        fm = QFontMetrics(self._timer_font())
        # Measure a normalised template, not the live text: digits become 0 so
        # the chip does not twitch wider as 9:59 rolls to 10:00, and the
        # separators become spaces because a space is the wider of the two --
        # which stops the blink from resizing the box every second.
        template = "".join(
            "0" if ch.isdigit() else " " for ch in self._timer_text()
        )
        icon = px(M.TIMER_ICON)
        # Frame + content padding on both sides, then icon, gap and digits.
        width = (
            px(painting.TIMER_CHIP_FRAME) * 2
            + px(2) * 2
            + icon
            + px(2)
            + fm.horizontalAdvance(template)
            + px(1)                       # a pixel of slack against rounding
        )
        height, _ = self._chip_metrics()
        if height < px(6):
            return None

        right = self._box_rect().left() - px(M.GAP)
        if self.task.priority > 0:
            right -= px(3) + px(M.GAP_SMALL)
        left = right - width
        if left - self._text_left() < px(M.TIMER_MIN_TEXT):
            return None                    # too cramped; the task text wins
        return QRect(left, (self.height() - height) // 2, width, height)

    def _timer_reached(self) -> bool:
        """Against the *live* elapsed, not the value last banked to the row."""
        return bool(self.task.timer_target) and self._elapsed >= self.task.timer_target

    def _timer_color(self):
        if self._timer_reached():
            return C.GREEN_BRIGHT
        if self._running:
            return C.YELLOW
        return C.TASK if self._elapsed else C.MUTED

    def _update_timer_tooltip(self) -> None:
        if not self.task.timer_enabled:
            self.setToolTip("")
            return
        spent = format_compact(self._elapsed) if self._elapsed else "0m"
        if self.task.timer_target:
            state = "running" if self._running else "paused"
            self.setToolTip(
                f"{spent} of {format_compact(self.task.timer_target)} ({state})"
            )
        else:
            self.setToolTip(f"{spent} tracked - click the clock to "
                            f"{'pause' if self._running else 'start'}")

    def _timer_progress(self) -> float:
        if not self.task.timer_target:
            # No goal: show a slow sweep so the bar still reads as a stopwatch.
            return (self._elapsed % 60) / 60.0 if self._elapsed else 0.0
        return min(1.0, self._elapsed / self.task.timer_target)

    # ------------------------------------------------------------------
    def _text_left(self) -> int:
        """Left edge of the task text column, after the optional icon."""
        x = px(M.GAP_SMALL)
        if self.show_icons:
            x += px(M.ICON_SIZE if not self.compact else M.ICON_SIZE - 3) + px(M.ICON_GAP)
        return x

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

        chip = self._chip_rect()
        if chip is not None:
            right_edge = chip.left() - px(M.GAP_SMALL)
            self._paint_timer_chip(p, chip)

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

    def _paint_timer_chip(self, p: QPainter, chip: QRect) -> None:
        reached = self._timer_reached()
        _, show_bar = self._chip_metrics()
        content = painting.draw_timer_chip(
            p, chip, self._timer_progress(), self._running, reached,
            self._hover_chip, show_bar,
        )
        if content.isEmpty():
            return

        color = self._timer_color()
        icon = px(M.TIMER_ICON)
        face = QRect(content.left(), content.top() + (content.height() - icon) // 2,
                     icon, icon)
        # Tinted flat, not in the icon's own palette: at seven pixels the
        # two-tone clock face is just noise next to the digits.
        draw_glyph(p, face, "clock", color)

        text_rect = QRect(
            face.right() + px(2),
            content.top(),
            max(0, content.right() - face.right() - px(2)),
            content.height(),
        )
        # No drop shadow here -- at this size it doubles every stroke and the
        # digits stop being readable. The recessed box supplies the contrast.
        painting.draw_text(
            p, text_rect, self._timer_text(), color, self._timer_font(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            shadow=False,
        )

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
        point = event.position().toPoint()
        inside = self._box_rect().adjusted(-px(2), -px(2), px(2), px(2)).contains(point)
        chip = self._hit_chip(point)
        if inside != self._hover_box or chip != self._hover_chip:
            self._hover_box = inside
            self._hover_chip = chip
            self.update()
        super().mouseMoveEvent(event)

    def _hit_chip(self, point: QPoint) -> bool:
        chip = self._chip_rect()
        return chip is not None and chip.adjusted(
            -px(2), -px(2), px(2), px(2)
        ).contains(point)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_box = False
        self._hover_chip = False
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
            # The chip owns its own clicks -- hitting the clock must never also
            # tick the task off.
            if self._hit_chip(event.position().toPoint()):
                self.timer_toggled.emit(self.task.id)
            else:
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
        if self._hit_chip(event.position().toPoint()):
            # Second click on the clock: just flip it back, no editor. The
            # first release toggled the timer, not the task, so there is
            # nothing to undo here.
            self.timer_toggled.emit(self.task.id)
            return
        self.toggled.emit(self.task.id)
        self.edit_requested.emit(self.task.id)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggled.emit(self.task.id)
            return
        if event.key() == Qt.Key.Key_F2:
            self.edit_requested.emit(self.task.id)
            return
        if event.key() == Qt.Key.Key_T and self.task.timer_enabled:
            self.timer_toggled.emit(self.task.id)
            return
        super().keyPressEvent(event)
