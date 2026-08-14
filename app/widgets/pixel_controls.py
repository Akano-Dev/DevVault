"""Reusable pixel-styled controls shared by the panel, dialogs and settings."""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QSlider,
    QWidget,
)

from ..core import painting
from ..core.theme import C, M, font, px


def paint_checkbox(
    p: QPainter,
    rect: QRect,
    checked: bool,
    hover: bool = False,
    anim: float | None = None,
) -> None:
    """Draw one checkbox in the reference's style.

    ``anim`` (0..1) drives the border's white-to-green transition and the check
    mark's fade. Callers that do not animate omit it, and it is derived from
    ``checked`` -- defaulting it to 1.0 would draw every box as ticked.
    """
    if anim is None:
        anim = 1.0 if checked else 0.0
    painting.draw_reference_checkbox(p, rect, checked, hover, anim)


class PixelCheckBox(QAbstractButton):
    """Checkbox + label, drawn entirely by hand."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._box = M.CHECK_SIZE

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(px(self._box) + px(M.GAP) + fm.horizontalAdvance(self.text()) + px(4),
                     max(px(self._box) + px(4), fm.height() + px(4)))

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)
        box = px(self._box)
        y = (self.height() - box) // 2
        paint_checkbox(p, QRect(0, y, box, box), self.isChecked(), self.underMouse())
        p.setFont(self.font())
        p.setPen(C.TASK if self.isEnabled() else C.MUTED)
        p.drawText(
            QRect(box + px(M.GAP), 0, self.width() - box - px(M.GAP), self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )
        p.end()


class PixelButton(QAbstractButton):
    """Blocky beveled button; inverts its bevel while pressed."""

    def __init__(self, text: str = "", parent: QWidget | None = None, danger: bool = False) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.danger = danger

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + px(20), fm.height() + px(12))

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)
        pressed = self.isDown()
        body = C.PANEL_ALT.lighter(140) if self.underMouse() else C.PANEL_ALT
        if pressed:
            painting.draw_inset_box(p, self.rect(), body.darker(115), px(2))
        else:
            painting.draw_bevel_panel(p, self.rect(), body, C.BEVEL_LIGHT, C.BEVEL_DARK,
                                      thickness=px(2))
        p.setFont(self.font())
        p.setPen(C.RED if self.danger else (C.GREEN_BRIGHT if self.underMouse() else C.TASK))
        p.drawText(self.rect().adjusted(0, px(1) if pressed else 0, 0, 0),
                   Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class PixelProgress(QWidget):
    """Segmented progress meter -- discrete cells, never a smooth web bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self.setFixedHeight(px(M.PROGRESS_HEIGHT) + px(4))

    def value(self) -> float:
        return self._value

    def setValue(self, value: float) -> None:  # noqa: N802 (Qt naming)
        value = max(0.0, min(1.0, float(value)))
        if abs(value - self._value) > 1e-4:
            self._value = value
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)
        h = px(M.PROGRESS_HEIGHT)
        trough = QRect(0, (self.height() - h) // 2, self.width(), h)
        p.fillRect(trough, C.BOX_FILL)
        inner = trough.adjusted(px(1), px(1), -px(1), -px(1))

        cells = M.PROGRESS_CELLS
        gap = max(1, px(1))
        cell_w = max(1, (inner.width() - gap * (cells - 1)) // cells)
        filled = int(round(self._value * cells))
        complete = self._value >= 0.999
        for i in range(cells):
            x = inner.left() + i * (cell_w + gap)
            if x + cell_w > inner.right() + 1:
                break
            if i < filled:
                color = C.GREEN if complete else C.YELLOW
            else:
                color = C.SEPARATOR
            p.fillRect(QRect(x, inner.top(), cell_w, inner.height()), color)
        p.end()


class PixelSlider(QSlider):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 100)
        self.setFixedHeight(px(18))
        self.setStyleSheet(
            f"""
            QSlider::groove:horizontal {{
                background: {C.PANEL.darker(140).name()};
                border: 1px solid {C.OUTLINE.name()};
                height: {px(6)}px;
            }}
            QSlider::sub-page:horizontal {{ background: {C.YELLOW_DIM.name()}; }}
            QSlider::handle:horizontal {{
                background: {C.YELLOW.name()};
                border: 1px solid {C.OUTLINE.name()};
                width: {px(8)}px;
                margin: -{px(4)}px 0;
            }}
            QSlider::handle:horizontal:hover {{ background: {C.TITLE.name()}; }}
            """
        )


def style_line_edit(widget: QLineEdit) -> QLineEdit:
    widget.setStyleSheet(
        f"""
        QLineEdit {{
            background: {C.BOX_FILL.name()};
            border: 1px solid {C.OUTLINE.name()};
            border-top: {px(2)}px solid {C.BEVEL_DARK.name()};
            border-left: {px(2)}px solid {C.BEVEL_DARK.name()};
            color: {C.TITLE.name()};
            padding: {px(4)}px {px(5)}px;
            selection-background-color: {C.GREEN_DARK.name()};
        }}
        QLineEdit:focus {{ border-bottom: {px(2)}px solid {C.GREEN.name()}; }}
        """
    )
    return widget


def style_combo(widget: QComboBox) -> QComboBox:
    widget.setStyleSheet(
        f"""
        QComboBox {{
            background: {C.BOX_FILL.name()};
            border: 1px solid {C.OUTLINE.name()};
            color: {C.TASK.name()};
            padding: {px(3)}px {px(5)}px;
        }}
        QComboBox:hover {{ color: {C.GREEN_BRIGHT.name()}; }}
        QComboBox::drop-down {{ border: none; width: {px(14)}px; }}
        QComboBox QAbstractItemView {{
            background: {C.PANEL.name()};
            border: 1px solid {C.OUTLINE.name()};
            color: {C.TASK.name()};
            selection-background-color: {C.GREEN_DARK.name()};
            outline: none;
        }}
        """
    )
    return widget


MENU_STYLE = f"""
QMenu {{
    background: {C.PANEL.name()};
    border: 1px solid {C.OUTLINE.name()};
    color: {C.TASK.name()};
    padding: {px(3)}px;
}}
QMenu::item {{ padding: {px(4)}px {px(14)}px; }}
QMenu::item:selected {{ background: {C.GREEN_DARK.name()}; color: {C.TITLE.name()}; }}
QMenu::item:disabled {{ color: {C.MUTED.name()}; }}
QMenu::separator {{ height: 1px; background: {C.SEPARATOR.name()}; margin: {px(3)}px 0; }}
"""
