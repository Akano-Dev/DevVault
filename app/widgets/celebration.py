"""Quest-completion flourish: a restrained fade-in banner over the panel."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QRect,
    QSequentialAnimationGroup,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ..core import painting
from ..core.theme import C, M, font, label_font, px

HOLD_MS = 1400
FADE_IN_MS = 260
FADE_OUT_MS = 420


class CelebrationOverlay(QWidget):
    """Non-interactive banner shown when every task in an objective is done."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._alpha = 0.0
        self._group: QSequentialAnimationGroup | None = None
        self._title = "OBJECTIVE COMPLETE"
        self._subtitle = "Quest Completed!"
        self.hide()

    def play(self, title: str = "", subtitle: str = "") -> None:
        if title:
            self._title = title
        if subtitle:
            self._subtitle = subtitle

        if self._group is not None:
            self._group.stop()

        self.resize(self.parentWidget().size())
        self.raise_()
        self.show()

        fade_in = QVariantAnimation(self)
        fade_in.setDuration(FADE_IN_MS)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade_in.valueChanged.connect(self._set_alpha)

        hold = QVariantAnimation(self)
        hold.setDuration(HOLD_MS)
        hold.setStartValue(1.0)
        hold.setEndValue(1.0)

        fade_out = QVariantAnimation(self)
        fade_out.setDuration(FADE_OUT_MS)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        fade_out.valueChanged.connect(self._set_alpha)

        group = QSequentialAnimationGroup(self)
        group.addAnimation(fade_in)
        group.addAnimation(hold)
        group.addAnimation(fade_out)
        group.finished.connect(self.hide)
        group.start()
        self._group = group

    def _set_alpha(self, value) -> None:
        self._alpha = float(value)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._alpha <= 0.0:
            return
        p = QPainter(self)
        painting.crisp(p)
        a = max(0.0, min(1.0, self._alpha))

        scrim = QColor(C.PANEL)
        scrim.setAlphaF(0.86 * a)
        p.fillRect(self.rect(), scrim)

        # Banner strip across the middle
        band_h = px(46)
        band = QRect(px(6), (self.height() - band_h) // 2, self.width() - px(12), band_h)
        body = QColor(C.PANEL_ALT)
        body.setAlphaF(a)
        border = QColor(C.GREEN_DARK)
        border.setAlphaF(a)
        inner = painting.draw_bevel_panel(
            p, band, body, border, border, outline=None, thickness=px(2)
        )

        title_color = QColor(C.GREEN_BRIGHT)
        title_color.setAlphaF(a)
        p.setFont(label_font(M.EYEBROW_SIZE + 2))
        p.setPen(title_color)
        p.drawText(
            QRect(inner.left(), inner.top() + px(6), inner.width(), px(14)),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self._title,
        )

        sub_color = QColor(C.TITLE)
        sub_color.setAlphaF(a)
        p.setFont(font(M.TASK_SIZE + 1))
        p.setPen(sub_color)
        p.drawText(
            QRect(inner.left(), inner.top() + px(22), inner.width(), px(18)),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self._subtitle,
        )
        p.end()
