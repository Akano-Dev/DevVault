"""The header card: item icon, yellow 'Current Objective', white objective name.

This is the widest element in the reference; the task card below is inset from
it on both sides.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ..core import painting
from ..core.icons import draw_glyph
from ..core.theme import C, M, font, px
from ..models.entities import Objective
from ..utils.dragging import try_start_drag

EYEBROW_TEXT = "Current Objective"
DEFAULT_ICON = "quest"


#: chrome buttons, right to left along the card's top-right corner
BUTTONS = (
    ("close", "ui_close", "Quit QuestPanel\nEsc or Ctrl+Shift+Q just hides it"),
    ("settings", "ui_gear", "Settings"),
    ("add", "ui_plus", "Add task"),
)
BUTTON_SIZE = 11
BUTTON_GAP = 4


class ObjectiveCard(QWidget):
    edit_requested = Signal()
    menu_requested = Signal(QPoint)
    add_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()      # the 'x' exits the app, it does not hide it

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.objective: Objective | None = None
        self.compact = compact
        self.icon_name = DEFAULT_ICON
        self._hover_button: str | None = None
        self._float_phase = 0.0
        self._floating = False
        self._icon_rect: QRect | None = None
        self._float_timer = QTimer(self)
        self._float_timer.setInterval(160)      # ~6fps is plenty for a 1px bob
        self._float_timer.timeout.connect(self._advance_float)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.mapToGlobal(pos))
        )
        self._recalc()

    # ------------------------------------------------------------------
    # Chrome buttons
    # ------------------------------------------------------------------
    def _button_rects(self) -> dict[str, QRect]:
        """Right-aligned along the top edge. Always visible: without a title
        bar these are the only way to close the overlay with the mouse."""
        size = px(BUTTON_SIZE)
        gap = px(BUTTON_GAP)
        top = px(M.CARD_PAD_Y) - px(2)
        right = self.width() - px(M.CARD_PAD_X)
        rects: dict[str, QRect] = {}
        for index, (name, _glyph, _tip) in enumerate(BUTTONS):
            x = right - size - index * (size + gap)
            rects[name] = QRect(x, top, size, size)
        return rects

    def _button_at(self, pos: QPoint) -> str | None:
        for name, rect in self._button_rects().items():
            if rect.adjusted(-px(2), -px(2), px(2), px(2)).contains(pos):
                return name
        return None

    def _paint_buttons(self, p: QPainter) -> None:
        rects = self._button_rects()
        for name, glyph, _tip in BUTTONS:
            rect = rects[name]
            hovered = self._hover_button == name
            if hovered:
                p.fillRect(rect.adjusted(-px(2), -px(2), px(2), px(2)), C.HOVER)
            color = C.RED if (hovered and name == "close") else (
                C.YELLOW if hovered else C.MUTED
            )
            draw_glyph(p, rect, glyph, color)

    def _leftmost_button_x(self) -> int:
        rects = self._button_rects()
        return min(r.left() for r in rects.values()) - px(M.GAP)

    # ------------------------------------------------------------------
    def _eyebrow_size(self) -> int:
        return M.EYEBROW_SIZE - (1 if self.compact else 0)

    def _title_size(self) -> int:
        return M.TITLE_SIZE - (2 if self.compact else 0)

    @staticmethod
    def _line_height(f) -> int:
        """Line box with slack.

        ``drawText`` clips to its rectangle, and some pixel faces draw beyond
        the metric height, which shears the tops off capitals. The slack costs
        nothing and makes the layout font-agnostic.
        """
        fm = QFontMetrics(f)
        return max(fm.height(), fm.tightBoundingRect("ÀCgjpq").height()) + px(3)

    def _recalc(self) -> None:
        """Measured, never guessed -- see the 150% DPI clipping bug."""
        self._eyebrow_h = self._line_height(font(self._eyebrow_size()))
        self._title_h = self._line_height(font(self._title_size()))
        pad = px(M.CARD_PAD_Y if not self.compact else M.CARD_PAD_Y - 2)
        text_h = self._eyebrow_h + px(M.HEADER_LINE_GAP) + self._title_h
        icon_h = px(M.HEADER_ICON if not self.compact else M.HEADER_ICON - 6)
        self.setFixedHeight(max(text_h, icon_h) + pad * 2)

    def set_objective(
        self, objective: Objective | None, compact: bool, animate: bool = True
    ) -> None:
        self.objective = objective
        self.compact = compact
        self._recalc()
        self.set_floating(animate)
        self.update()

    def set_floating(self, floating: bool) -> None:
        """Idle bob, off when animations are disabled."""
        if floating == self._floating:
            return
        self._floating = floating
        if floating:
            self._float_timer.start()
        else:
            self._float_timer.stop()
            self._float_phase = 0.0
        self.update()

    def _advance_float(self) -> None:
        if not self.isVisible():
            return
        self._float_phase = (self._float_phase + 0.22) % math.tau
        # Repaint the icon only. update() on the whole card forces a full
        # recomposite of the translucent window, which measured 3.9% CPU for a
        # one-pixel bob -- an absurd price for the effect.
        if self._icon_rect is not None:
            self.update(self._icon_rect.adjusted(-px(2), -px(3), px(2), px(3)))
        else:
            self.update()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._float_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._floating:
            self._float_timer.start()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(px(200), self.height())

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        inner = painting.draw_card(p, self.rect())
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        pad_x = px(M.CARD_PAD_X)
        pad_y = px(M.CARD_PAD_Y if not self.compact else M.CARD_PAD_Y - 2)
        x = inner.left() + pad_x

        icon = px(M.HEADER_ICON if not self.compact else M.HEADER_ICON - 6)
        # A slow 1px bob so the panel is never completely dead on screen.
        bob = int(round(math.sin(self._float_phase) * px(1))) if self._floating else 0
        icon_rect = QRect(x, inner.top() + (inner.height() - icon) // 2 + bob, icon, icon)
        self._icon_rect = icon_rect
        name = self.icon_name or DEFAULT_ICON
        if draw_glyph(p, icon_rect, name):
            x = icon_rect.right() + px(M.HEADER_ICON_GAP)

        text_h = self._eyebrow_h + px(M.HEADER_LINE_GAP) + self._title_h
        y = inner.top() + max(pad_y, (inner.height() - text_h) // 2)
        width = max(0, inner.right() - x - pad_x)
        # The eyebrow shares its line with the chrome buttons.
        eyebrow_width = max(0, min(width, self._leftmost_button_x() - x))

        eyebrow_font = font(self._eyebrow_size())
        painting.draw_text(
            p, QRect(x, y, eyebrow_width, self._eyebrow_h),
            EYEBROW_TEXT, C.EYEBROW, eyebrow_font,
        )
        self._paint_buttons(p)

        y += self._eyebrow_h + px(M.HEADER_LINE_GAP)
        title_font = font(self._title_size())
        p.setFont(title_font)
        title = self.objective.title if self.objective else "No Objective"
        title = QFontMetrics(title_font).elidedText(
            title, Qt.TextElideMode.ElideRight, width
        )
        painting.draw_text(p, QRect(x, y, width, self._title_h), title, C.TITLE, title_font)
        p.end()

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            name = self._button_at(event.position().toPoint())
            if name is not None:
                {
                    "add": self.add_requested,
                    "settings": self.settings_requested,
                    "close": self.quit_requested,
                }[name].emit()
                return
        if not try_start_drag(self, event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        name = self._button_at(event.position().toPoint())
        if name != self._hover_button:
            self._hover_button = name
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if name
                else Qt.CursorShape.ArrowCursor
            )
            self.setToolTip(
                next((t for n, _g, t in BUTTONS if n == name), "") if name
                else "Double-click to edit  |  Right-click for menu"
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_button is not None:
            self._hover_button = None
            self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._button_at(event.position().toPoint()) is not None:
            return
        self.edit_requested.emit()
