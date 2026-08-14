"""Original pixel-art glyphs, drawn at runtime from 8x8 bitmaps.

Nothing here is a bundled image file: the icons are defined as ASCII grids so
the application ships with zero third-party artwork and stays crisp at any
DPI. Users may still drop their own PNGs into ``assets/icons`` -- those are
picked up by :func:`custom_icon_names`.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from .paths import asset
from .theme import C

# Grid legend:  '.' transparent  |  'X' primary  |  'o' secondary  |  '+' accent
GLYPHS: dict[str, tuple[str, ...]] = {
    "quest": (
        "...XX...",
        "..XXXX..",
        ".XXXXXX.",
        "XXX..XXX",
        "XXX..XXX",
        ".XXXXXX.",
        "..XXXX..",
        "...XX...",
    ),
    "sword": (
        "......XX",
        ".....XX.",
        "....XX..",
        "...XX...",
        "..XX....",
        ".oXo....",
        "oo.o....",
        "o.......",
    ),
    "pickaxe": (
        ".XXX.XXX",
        "X..XXX..",
        "...oo...",
        "..oo....",
        "..o.....",
        ".o......",
        ".o......",
        "o.......",
    ),
    "book": (
        ".XXXXXX.",
        ".XoooooX",
        ".XoXXXoX",
        ".XoooooX",
        ".XoXXXoX",
        ".XoooooX",
        ".XXXXXX.",
        "........",
    ),
    "star": (
        "...XX...",
        "...XX...",
        "XXXXXXXX",
        ".XXXXXX.",
        "..XXXX..",
        "..X..X..",
        ".X....X.",
        "........",
    ),
    "flame": (
        "...XX...",
        "..XXXX..",
        "..XXXX..",
        ".XX++XX.",
        "XX+++XXX",
        "XX+++XXX",
        ".XX++XX.",
        "..XXXX..",
    ),
    "heart": (
        ".XX..XX.",
        "XXXXXXXX",
        "XXXXXXXX",
        "XXXXXXXX",
        ".XXXXXX.",
        "..XXXX..",
        "...XX...",
        "........",
    ),
    "gear": (
        "..X..X..",
        ".XXXXXX.",
        "XXX..XXX",
        "XX....XX",
        "XX....XX",
        "XXX..XXX",
        ".XXXXXX.",
        "..X..X..",
    ),
    "clock": (
        "..XXXX..",
        ".XooooX.",
        "XooXoooX",
        "XooXoooX",
        "XooXXooX",
        "XooooooX",
        ".XooooX.",
        "..XXXX..",
    ),
    "potion": (
        "..XXXX..",
        "...XX...",
        "..XXXX..",
        ".XX++XX.",
        "X++++++X",
        "X++++++X",
        "X++++++X",
        ".XXXXXX.",
    ),
    # --- UI control glyphs (not offered as task icons) ---
    "ui_plus": (
        "........",
        "...XX...",
        "...XX...",
        ".XXXXXX.",
        ".XXXXXX.",
        "...XX...",
        "...XX...",
        "........",
    ),
    "ui_close": (
        "........",
        ".X....X.",
        "..X..X..",
        "...XX...",
        "...XX...",
        "..X..X..",
        ".X....X.",
        "........",
    ),
    "ui_gear": (
        "..X..X..",
        ".XXXXXX.",
        "XXX..XXX",
        "XX....XX",
        "XX....XX",
        "XXX..XXX",
        ".XXXXXX.",
        "..X..X..",
    ),
}

# Glyphs reserved for chrome -- excluded from the task icon picker.
UI_GLYPHS = ("ui_plus", "ui_close", "ui_gear")

ICON_NAMES = ("",) + tuple(n for n in GLYPHS if n not in UI_GLYPHS)


# Each glyph gets its own (primary, secondary, accent) palette so the row icons
# read as colourful items, the way the reference does. All original artwork.
PALETTES: dict[str, tuple[QColor, QColor, QColor]] = {
    "quest":   (QColor(0x4D, 0xE2, 0xD5), QColor(0x2A, 0x9D, 0x93), QColor(0xB8, 0xFF, 0xF7)),
    "sword":   (QColor(0x7A, 0xA8, 0xE8), QColor(0x8B, 0x6A, 0x3E), QColor(0xCB, 0xE0, 0xFF)),
    "pickaxe": (QColor(0xC9, 0xCE, 0xD6), QColor(0x8B, 0x6A, 0x3E), QColor(0xF0, 0xF3, 0xF7)),
    "book":    (QColor(0xC0, 0x50, 0x3A), QColor(0xE8, 0xDE, 0xC0), QColor(0xFF, 0xF6, 0xDC)),
    "star":    (QColor(0xFC, 0xE0, 0x50), QColor(0xC9, 0xA0, 0x20), QColor(0xFF, 0xF6, 0xB0)),
    "flame":   (QColor(0x8B, 0x3F, 0xC4), QColor(0x5B, 0x1F, 0x8C), QColor(0xC9, 0x7B, 0xFF)),
    "heart":   (QColor(0xE0, 0x3B, 0x3B), QColor(0x9B, 0x1F, 0x1F), QColor(0xFF, 0x8A, 0x8A)),
    "gear":    (QColor(0xA8, 0xAE, 0xB8), QColor(0x6B, 0x70, 0x78), QColor(0xDD, 0xE2, 0xEA)),
    "clock":   (QColor(0xE8, 0xC8, 0x6A), QColor(0x3A, 0x5A, 0xA8), QColor(0xFF, 0xF0, 0xC0)),
    "potion":  (QColor(0x4D, 0xE2, 0xD5), QColor(0x2A, 0x9D, 0x93), QColor(0x9B, 0xF0, 0xE8)),
}

DEFAULT_PALETTE = (QColor(0xCC, 0xCC, 0xCC), QColor(0x88, 0x88, 0x88), QColor(0xF0, 0xF0, 0xF0))


def _paint_glyph(
    p: QPainter,
    rect: QRect,
    grid: tuple[str, ...],
    primary: QColor,
    secondary: QColor | None = None,
    accent: QColor | None = None,
) -> None:
    rows = len(grid)
    cols = max(len(r) for r in grid)
    unit_w = max(1, rect.width() // cols)
    unit_h = max(1, rect.height() // rows)
    ox = rect.left() + (rect.width() - unit_w * cols) // 2
    oy = rect.top() + (rect.height() - unit_h * rows) // 2
    sec = secondary or primary.darker(150)
    acc = accent or primary.lighter(150)
    lookup = {"X": primary, "o": sec, "+": acc}
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            color = lookup.get(ch)
            if color is not None:
                p.fillRect(QRect(ox + x * unit_w, oy + y * unit_h, unit_w, unit_h), color)


def draw_glyph(
    p: QPainter, rect: QRect, name: str, color: QColor | None = None
) -> bool:
    """Draw a built-in glyph or a user-supplied PNG. Returns False if unknown.

    Passing ``color`` forces a monochrome tint (used in menus); omitting it
    renders the icon in its own colours, as the reference does.
    """
    if not name:
        return False
    grid = GLYPHS.get(name)
    if grid is not None:
        if color is not None:
            _paint_glyph(p, rect, grid, color)
        else:
            primary, secondary, accent = PALETTES.get(name, DEFAULT_PALETTE)
            _paint_glyph(p, rect, grid, primary, secondary, accent)
        return True
    pm = _custom_pixmap(name, rect.width(), rect.height())
    if pm is not None:
        p.drawPixmap(rect.topLeft(), pm)
        return True
    return False


@lru_cache(maxsize=64)
def _custom_pixmap(name: str, w: int, h: int) -> QPixmap | None:
    path = asset("icons", f"{name}.png")
    if not path.is_file():
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.FastTransformation)


def custom_icon_names() -> list[str]:
    """PNG basenames the user dropped into ``assets/icons``."""
    d = asset("icons")
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.png"))


def glyph_pixmap(name: str, size: int, color: QColor | None = None) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    draw_glyph(p, QRect(0, 0, size, size), name, color)
    p.end()
    return pm


def app_icon() -> QIcon:
    """Window/tray icon: a green quest diamond on a dark beveled tile."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        u = max(1, size // 16)
        p.fillRect(QRect(0, 0, size, size), C.OUTLINE)
        p.fillRect(QRect(u, u, size - 2 * u, size - 2 * u), C.BEVEL_DARK)
        p.fillRect(QRect(2 * u, 2 * u, size - 4 * u, size - 4 * u), C.PANEL)
        _paint_glyph(
            p,
            QRect(2 * u, 2 * u, size - 4 * u, size - 4 * u),
            GLYPHS["quest"],
            C.GREEN,
            C.GREEN_DARK,
        )
        p.end()
        icon.addPixmap(pm)
    return icon
