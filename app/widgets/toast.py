"""Pixel-art desktop notifications, drawn by QuestPanel rather than Windows.

The native tray toast works, but it is a Windows 11 card with rounded corners,
a system font and the host process's name on it -- "Python", in a dev run. That
is the wrong app wearing the wrong clothes, so this draws the notification in
the panel's own language instead: a beveled slot, the pixel face, a glyph, and
a durability bar that drains as the toast times out.

Toasts are separate frameless always-on-top windows. They never take focus, so
one arriving mid-sentence cannot steal a keystroke.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QRect,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from ..core import painting
from ..core.icons import draw_glyph
from ..core.theme import C, M, font, label_font, px

# Design pixels, scaled at paint time like every other metric in the app.
TOAST_W = 272
TOAST_H = 58
TOAST_MARGIN = 12          # gap from the screen's top-right corner
TOAST_GAP = 6              # gap between stacked toasts
TOAST_ICON = 24
TOAST_PAD = 8
LIFETIME_MS = 5000
SLIDE_MS = 220


def _wrap(fm: QFontMetrics, text: str, width: int, max_lines: int) -> list[str]:
    """Greedy word wrap, eliding whatever will not fit in the last line."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if fm.horizontalAdvance(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    # Everything past the last allowed line is folded back into it, so the
    # elision reads as "there is more" rather than silently dropping words.
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    lines[-1] = fm.elidedText(lines[-1], Qt.TextElideMode.ElideRight, width)
    return lines


class PixelToast(QWidget):
    """One notification window."""

    activated = Signal()
    finished = Signal(object)      # emits self so the stack can drop it

    def __init__(
        self,
        title: str,
        body: str,
        icon: str = "quest",
        lifetime_ms: int = LIFETIME_MS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(None)
        self.title = title
        self.body = body
        self.icon = icon
        self.lifetime_ms = max(1200, int(lifetime_ms))
        self._remaining = float(self.lifetime_ms)
        self._hovered = False
        self._closing = False
        self._slide = 0.0              # 0 = fully off-screen right, 1 = parked

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFixedSize(px(TOAST_W), px(TOAST_H))

        self._parked = QPoint(0, 0)
        self._anim: QVariantAnimation | None = None

        # One timer drives both the countdown and the draining bar.
        self._tick = QTimer(self)
        self._tick.setInterval(40)
        self._tick.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------
    def park_at(self, point: QPoint, animate: bool = True) -> None:
        """Set the resting position, sliding there if already visible."""
        self._parked = QPoint(point)
        if not self.isVisible():
            self.move(self._offscreen_point())
            return
        if animate and not self._closing:
            self.move(self._point_for(self._slide))
        else:
            self.move(self._parked)

    def _offscreen_point(self) -> QPoint:
        return QPoint(self._parked.x() + self.width() + px(TOAST_MARGIN), self._parked.y())

    def _point_for(self, slide: float) -> QPoint:
        start = self._offscreen_point()
        x = start.x() + (self._parked.x() - start.x()) * max(0.0, min(1.0, slide))
        return QPoint(int(round(x)), self._parked.y())

    # ------------------------------------------------------------------
    def show_toast(self) -> None:
        self.move(self._offscreen_point())
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._animate(0.0, 1.0, SLIDE_MS, QEasingCurve.Type.OutCubic)
        self._tick.start()

    def dismiss(self) -> None:
        """Slide back out and report finished. Idempotent."""
        if self._closing:
            return
        self._closing = True
        self._tick.stop()
        self._animate(self._slide, 0.0, SLIDE_MS, QEasingCurve.Type.InCubic,
                      on_done=self._on_closed)

    def _animate(self, start, end, duration, curve, on_done=None) -> None:
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setDuration(duration)
        anim.setEasingCurve(curve)
        anim.valueChanged.connect(self._on_slide)
        if on_done is not None:
            anim.finished.connect(on_done)
        anim.start()
        self._anim = anim

    def _on_slide(self, value) -> None:
        self._slide = float(value)
        self.setWindowOpacity(max(0.0, min(1.0, self._slide)))
        self.move(self._point_for(self._slide))

    def _on_closed(self) -> None:
        self.hide()
        self.finished.emit(self)

    # ------------------------------------------------------------------
    def _on_tick(self) -> None:
        # Hovering holds the toast open: the user is plainly reading it.
        if not self._hovered:
            self._remaining -= self._tick.interval()
        self.update()
        if self._remaining <= 0:
            self.dismiss()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # The right-hand strip is a dismiss button; the rest activates.
            if self._close_rect().contains(event.position().toPoint()):
                self.dismiss()
            else:
                self.activated.emit()
                self.dismiss()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    def _close_rect(self) -> QRect:
        size = px(9)
        return QRect(self.width() - px(TOAST_PAD) - size, px(TOAST_PAD), size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)

        body_color = C.PANEL_SOLID.lighter(112) if self._hovered else C.PANEL_SOLID
        inner = painting.draw_bevel_panel(p, self.rect(), body_color, thickness=px(2))

        pad = px(TOAST_PAD)
        icon_size = px(TOAST_ICON)
        icon_rect = QRect(inner.left() + pad, inner.top() + (inner.height() - icon_size) // 2,
                          icon_size, icon_size)
        draw_glyph(p, icon_rect, self.icon)

        text_left = icon_rect.right() + px(M.GAP)
        text_right = inner.right() - pad - px(11)      # room for the close cross
        text_width = max(px(20), text_right - text_left)

        # Tighter tracking than the panel's headings: a toast title is a whole
        # sentence, and label_font's default spacing elides it after a word.
        title_font = label_font(M.SECTION_SIZE, letter_spacing=0.4)
        p.setFont(title_font)
        title_fm = QFontMetrics(title_font)
        title_rect = QRect(text_left, inner.top() + pad, text_width, title_fm.height())
        painting.draw_text(
            p, title_rect,
            title_fm.elidedText(self.title.upper(), Qt.TextElideMode.ElideRight, text_width),
            C.EYEBROW, title_font,
        )

        body_font = font(M.TASK_SIZE_COMPACT)
        body_fm = QFontMetrics(body_font)
        y = title_rect.bottom() + px(2)
        for line in _wrap(body_fm, self.body, text_width, 2):
            line_rect = QRect(text_left, y, text_width, body_fm.height())
            painting.draw_text(p, line_rect, line, C.TASK, body_font)
            y += body_fm.height()

        # Dismiss cross, in the same 8x8 glyph language as the panel header.
        draw_glyph(p, self._close_rect(), "ui_close",
                   C.TASK if self._hovered else C.MUTED)

        # Lifetime bar along the bottom edge, drawn exactly like the timer
        # chip's durability bar so the two read as one family.
        bar_h = max(1, px(2))
        bar = QRect(inner.left(), inner.bottom() - bar_h + 1, inner.width(), bar_h)
        p.fillRect(bar, C.BEVEL_DARK)
        left = max(0.0, min(1.0, self._remaining / self.lifetime_ms))
        if left > 0.0:
            cell = max(1, px(3))
            gap = max(1, px(1))
            step = cell + gap
            cells = max(1, (bar.width() + gap) // step)
            lit = max(1, int(round(left * cells)))
            color = C.YELLOW_DIM if self._hovered else C.YELLOW
            for i in range(lit):
                x = bar.left() + i * step
                if x + cell > bar.right() + 1:
                    break
                p.fillRect(QRect(x, bar.top(), cell, bar_h), color)
        p.end()


class ToastStack:
    """Owns the live toasts and keeps them stacked in the top-right corner."""

    def __init__(self, max_visible: int = 3) -> None:
        self.max_visible = max_visible
        self._toasts: list[PixelToast] = []

    def show(
        self,
        title: str,
        body: str,
        icon: str = "quest",
        lifetime_ms: int = LIFETIME_MS,
        on_activated=None,
    ) -> PixelToast | None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None

        # Oldest goes first when the corner is full, so the newest is always
        # the one nearest the top.
        while len(self._toasts) >= self.max_visible:
            self._toasts[0].dismiss()
            self._drop(self._toasts[0])

        toast = PixelToast(title, body, icon, lifetime_ms)
        toast.finished.connect(self._on_finished)
        if on_activated is not None:
            toast.activated.connect(on_activated)
        self._toasts.append(toast)
        self._layout(screen)
        toast.show_toast()
        return toast

    def _layout(self, screen=None) -> None:
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        y = area.top() + px(TOAST_MARGIN)
        for toast in self._toasts:
            x = area.right() - toast.width() - px(TOAST_MARGIN) + 1
            toast.park_at(QPoint(x, y))
            y += toast.height() + px(TOAST_GAP)

    def _on_finished(self, toast: PixelToast) -> None:
        self._drop(toast)
        self._layout()

    def _drop(self, toast: PixelToast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
            toast.deleteLater()

    def clear(self) -> None:
        for toast in list(self._toasts):
            toast.hide()
            self._drop(toast)

    @property
    def count(self) -> int:
        return len(self._toasts)

    @property
    def toasts(self) -> tuple[PixelToast, ...]:
        """The live toasts, oldest first (so the last one is the newest)."""
        return tuple(self._toasts)
