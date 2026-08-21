"""Low-level pixel-art drawing helpers shared by every custom widget."""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen

from .theme import C, M, px


def draw_card(
    p: QPainter,
    rect: QRect,
    body: QColor | None = None,
    border: QColor | None = None,
    radius: int | None = None,
) -> QRect:
    """Reference-style card: flat dark fill inside a 1px light outline.

    Corners are rounded by a couple of pixels -- enough to soften the shape
    without reading as a modern rounded card.
    """
    body = body if body is not None else C.PANEL
    border = border if border is not None else C.CARD_BORDER
    r = px(M.RADIUS) if radius is None else radius

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(border, px(M.BORDER)))
    p.setBrush(QBrush(body))
    half = px(M.BORDER) / 2.0
    p.drawRoundedRect(QRectF(rect).adjusted(half, half, -half, -half), r, r)
    p.restore()

    inset = px(M.BORDER)
    return rect.adjusted(inset, inset, -inset, -inset)


def draw_text(
    p: QPainter,
    rect: QRect,
    text: str,
    color: QColor,
    font: QFont | None = None,
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
    shadow: bool = True,
) -> None:
    """Draw text with the 1px offset drop shadow the reference uses."""
    if font is not None:
        p.setFont(font)
    if shadow:
        offset = max(1, px(1))
        p.setPen(C.SHADOW)
        p.drawText(rect.translated(offset, offset), alignment, text)
    p.setPen(color)
    p.drawText(rect, alignment, text)


def draw_reference_checkbox(
    p: QPainter,
    rect: QRect,
    checked: bool,
    hover: bool = False,
    anim: float | None = None,
) -> None:
    """Square box with a thick border: white when open, green when checked."""
    border_w = max(1, px(M.CHECK_BORDER))
    # `anim` expresses "how checked" the box is (1 = done, 0 = open) and animates
    # in both directions. When omitted it follows `checked` -- defaulting it to
    # 1.0 would paint every unchecked box as ticked.
    if anim is None:
        anim = 1.0 if checked else 0.0
    fade = max(0.0, min(1.0, anim))

    open_color = QColor(C.BOX_BORDER)
    done_color = QColor(C.GREEN)
    border = QColor(
        int(open_color.red() + (done_color.red() - open_color.red()) * fade),
        int(open_color.green() + (done_color.green() - open_color.green()) * fade),
        int(open_color.blue() + (done_color.blue() - open_color.blue()) * fade),
    )
    if hover:
        border = border.lighter(115)

    p.fillRect(rect, C.BOX_FILL)
    # Four edges drawn as rects so the border stays perfectly square.
    p.fillRect(QRect(rect.left(), rect.top(), rect.width(), border_w), border)
    p.fillRect(QRect(rect.left(), rect.bottom() - border_w + 1, rect.width(), border_w), border)
    p.fillRect(QRect(rect.left(), rect.top(), border_w, rect.height()), border)
    p.fillRect(QRect(rect.right() - border_w + 1, rect.top(), border_w, rect.height()), border)

    if fade > 0.0:
        inner = rect.adjusted(border_w, border_w, -border_w, -border_w)
        draw_pixel_check(p, inner, C.GREEN, fade)


def fill(p: QPainter, rect: QRect, color: QColor) -> None:
    p.fillRect(rect, color)


def draw_bevel_panel(
    p: QPainter,
    rect: QRect,
    body: QColor = C.PANEL,
    light: QColor = C.BEVEL_LIGHT,
    dark: QColor = C.BEVEL_DARK,
    outline: QColor | None = C.OUTLINE,
    thickness: int | None = None,
) -> QRect:
    """Draw a hard-edged beveled panel and return the inner content rect.

    Structure, outside-in: 1px black outline, then ``thickness`` px of bevel
    (light on the top/left edges, dark on the bottom/right), then the body
    fill. No anti-aliasing, no rounding -- the edges must stay crisp.
    """
    t = thickness if thickness is not None else px(3)
    r = QRect(rect)

    if outline is not None:
        p.fillRect(r, outline)
        r = r.adjusted(px(1), px(1), -px(1), -px(1))

    # Bevel ring
    p.fillRect(QRect(r.left(), r.top(), r.width(), t), light)
    p.fillRect(QRect(r.left(), r.top(), t, r.height()), light)
    p.fillRect(QRect(r.left(), r.bottom() - t + 1, r.width(), t), dark)
    p.fillRect(QRect(r.right() - t + 1, r.top(), t, r.height()), dark)

    inner = r.adjusted(t, t, -t, -t)
    p.fillRect(inner, body)
    return inner


def draw_inset_box(p: QPainter, rect: QRect, body: QColor, t: int | None = None) -> QRect:
    """Inverse bevel -- used for checkboxes and progress troughs."""
    t = t if t is not None else px(1)
    r = QRect(rect)
    p.fillRect(r, C.OUTLINE)
    r = r.adjusted(px(1), px(1), -px(1), -px(1))
    p.fillRect(QRect(r.left(), r.top(), r.width(), t), C.BEVEL_DARK)
    p.fillRect(QRect(r.left(), r.top(), t, r.height()), C.BEVEL_DARK)
    p.fillRect(QRect(r.left(), r.bottom() - t + 1, r.width(), t), C.BEVEL_LIGHT)
    p.fillRect(QRect(r.right() - t + 1, r.top(), t, r.height()), C.BEVEL_LIGHT)
    inner = r.adjusted(t, t, -t, -t)
    p.fillRect(inner, body)
    return inner


TIMER_CHIP_FRAME = 2       # design px of outline + bevel on each edge
TIMER_CHIP_BAR = 3         # design px the durability bar and its gap need


def draw_timer_chip(
    p: QPainter,
    rect: QRect,
    progress: float,
    running: bool,
    reached: bool = False,
    hover: bool = False,
    show_bar: bool = True,
) -> QRect:
    """The task timer read-out: an inset slot with a durability bar.

    Built from the same pieces as the rest of the panel -- a recessed box and
    a segmented meter -- so it reads as an item slot rather than a web badge.
    Returns the rect the caller should draw the clock and digits into.

    ``show_bar`` is off when the row is too short to give the meter its own
    pixels; the digits then carry the state on their own.
    """
    body = C.BOX_FILL.lighter(140) if hover else C.BOX_FILL
    inner = draw_inset_box(p, rect, body, px(1))

    if not show_bar:
        return QRect(
            inner.left() + px(2), inner.top(),
            max(0, inner.width() - px(4)), inner.height(),
        )

    bar_h = max(1, px(2))
    bar = QRect(inner.left(), inner.bottom() - bar_h + 1, inner.width(), bar_h)
    p.fillRect(bar, C.BEVEL_DARK)

    progress = max(0.0, min(1.0, float(progress)))
    if progress > 0.0:
        color = C.GREEN if reached else (C.YELLOW if running else C.YELLOW_DIM)
        cell = max(1, px(2))
        gap = max(1, px(1))
        step = cell + gap
        cells = max(1, (bar.width() + gap) // step)
        # A started timer always lights at least one cell, so "running but
        # barely begun" never looks identical to "not started".
        filled = max(1, int(round(progress * cells)))
        for i in range(filled):
            x = bar.left() + i * step
            if x + cell > bar.right() + 1:
                break
            p.fillRect(QRect(x, bar.top(), cell, bar_h), color)

    return QRect(
        inner.left() + px(2),
        inner.top(),
        max(0, inner.width() - px(4)),
        max(0, inner.height() - bar_h - px(1)),
    )


def draw_pixel_check(p: QPainter, rect: QRect, color: QColor, alpha: float = 1.0) -> None:
    """A blocky check mark built from square cells on a 7x7 grid."""
    if alpha <= 0.0:
        return
    cells = [
        (1, 3), (1, 4),
        (2, 4), (2, 5),
        (3, 5),
        (3, 4), (4, 3), (5, 2), (6, 1),
        (4, 4), (5, 3), (6, 2),
    ]
    unit_w = max(1, rect.width() // 7)
    unit_h = max(1, rect.height() // 7)
    ox = rect.left() + (rect.width() - unit_w * 7) // 2
    oy = rect.top() + (rect.height() - unit_h * 7) // 2

    c = QColor(color)
    if alpha < 1.0:
        c.setAlphaF(max(0.0, min(1.0, alpha)))
    for cx, cy in cells:
        p.fillRect(QRect(ox + cx * unit_w, oy + cy * unit_h, unit_w, unit_h), c)


def draw_pixel_diamond(p: QPainter, rect: QRect, color: QColor) -> None:
    """Small blocky diamond used as the objective bullet."""
    n = 5
    unit = max(1, min(rect.width(), rect.height()) // n)
    ox = rect.left() + (rect.width() - unit * n) // 2
    oy = rect.top() + (rect.height() - unit * n) // 2
    widths = [1, 3, 5, 3, 1]
    for row, w in enumerate(widths):
        start = (n - w) // 2
        p.fillRect(QRect(ox + start * unit, oy + row * unit, w * unit, unit), color)


def draw_hline(p: QPainter, x1: int, x2: int, y: int, color: QColor, h: int | None = None) -> None:
    p.fillRect(QRect(x1, y, x2 - x1, h or px(1)), color)


def crisp(p: QPainter) -> None:
    """Disable smoothing so everything stays on the pixel grid."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    p.setPen(QPen(C.OUTLINE))
