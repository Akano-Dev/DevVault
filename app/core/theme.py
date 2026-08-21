"""Single source of truth for colours, metrics and fonts.

Everything visual is defined here so the whole look can be retuned from one
file. Metrics are expressed in *design pixels* and multiplied by the user's
UI scale at paint time via :func:`px`.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

from .paths import asset


# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
class C:
    """Sampled from the reference: a near-black card, yellow headings, #CCCCCC
    body text, and a bright green check state."""

    # Cards
    PANEL = QColor(0x21, 0x21, 0x21, 0xF2)      # card body, slightly translucent
    PANEL_SOLID = QColor(0x21, 0x21, 0x21)
    PANEL_ALT = QColor(0x2B, 0x2B, 0x2B)
    CARD_BORDER = QColor(0x4A, 0x4A, 0x4A)      # 1px light outline around a card
    CARD_BORDER_SOFT = QColor(0x3A, 0x3A, 0x3A)
    OUTLINE = QColor(0x00, 0x00, 0x00)

    # Type
    EYEBROW = QColor(0xFC, 0xFC, 0x54)          # "Current Objective"
    TITLE = QColor(0xFF, 0xFF, 0xFF)            # objective name
    SECTION = QColor(0xFC, 0xFC, 0x54)          # section headings
    TASK = QColor(0xCC, 0xCC, 0xCC)             # task text
    TASK_DONE = QColor(0xCC, 0xCC, 0xCC)        # reference does not dim completed text
    MUTED = QColor(0x80, 0x80, 0x80)
    SHADOW = QColor(0x00, 0x00, 0x00, 0xB4)     # Minecraft-style 1px text shadow

    # Accents
    YELLOW = QColor(0xFC, 0xFC, 0x54)
    YELLOW_DIM = QColor(0xA8, 0xA8, 0x38)
    GREEN = QColor(0x54, 0xFC, 0x54)            # checked box border + tick
    GREEN_BRIGHT = QColor(0x8C, 0xFF, 0x8C)
    GREEN_DARK = QColor(0x2A, 0x7A, 0x2A)
    GOLD = QColor(0xFF, 0xAA, 0x00)
    RED = QColor(0xFF, 0x55, 0x55)

    # Interaction
    HOVER = QColor(0xFF, 0xFF, 0xFF, 20)
    SEPARATOR = QColor(0x3A, 0x3A, 0x3A)

    # Checkbox
    BOX_FILL = QColor(0x1A, 0x1A, 0x1A)
    BOX_FILL_DONE = QColor(0x1A, 0x1A, 0x1A)
    BOX_BORDER = QColor(0xFF, 0xFF, 0xFF)       # unchecked outline

    # Back-compat aliases for the beveled controls (buttons, sliders, dialogs)
    BEVEL_LIGHT = QColor(0x4A, 0x4A, 0x4A)
    BEVEL_DARK = QColor(0x18, 0x18, 0x18)


PRIORITY_COLORS = {
    0: C.MUTED,
    1: C.GREEN,
    2: C.GOLD,
    3: C.RED,
}
PRIORITY_NAMES = {0: "None", 1: "Low", 2: "Medium", 3: "High"}


# --------------------------------------------------------------------------
# Metrics (design pixels @ scale 1.0)
# --------------------------------------------------------------------------
class M:
    """Design pixels, derived from the reference at ~1.8x its 208px width.

    The reference is two stacked cards: a wide header card carrying the item
    icon and two lines of text, and a narrower body card, inset on the left and
    right, holding the section headings and task rows.
    """

    BORDER = 1               # cards use a 1px light outline, not a heavy bevel
    RADIUS = 3               # subtle rounded corner on each card

    # Header card
    CARD_PAD_X = 9
    CARD_PAD_Y = 7
    HEADER_ICON = 26         # the big objective item icon
    HEADER_ICON_GAP = 9
    HEADER_LINE_GAP = 2

    # Body card -- inset from the header card on both sides
    BODY_INSET_LEFT = 15
    BODY_INSET_RIGHT = 13
    BODY_PAD_X = 8
    BODY_PAD_TOP = 5
    BODY_PAD_BOTTOM = 6
    CARD_GAP = 0             # the cards touch, as in the reference

    EYEBROW_SIZE = 13
    TITLE_SIZE = 15
    SECTION_SIZE = 12
    TASK_SIZE = 13

    # Compact mode drops the type a step as well as the padding -- trimming
    # padding alone only saves a pixel a row, which is not worth a setting.
    SECTION_SIZE_COMPACT = 10
    TASK_SIZE_COMPACT = 11

    ROW_HEIGHT = 20
    ROW_HEIGHT_COMPACT = 15
    CHECK_SIZE = 14
    CHECK_BORDER = 2
    ICON_SIZE = 17
    ICON_GAP = 7
    CHECK_MARGIN = 5         # gap between the checkbox column and the card edge

    # Task timer chip. The digits are set in the LABEL face: the body face
    # garbles numerals this small (a 5 comes out looking like an 8).
    TIMER_SIZE = 9
    TIMER_SIZE_COMPACT = 8
    TIMER_ICON = 7           # the little clock face in the chip
    TIMER_MIN_TEXT = 30      # below this much text room the chip is dropped

    GAP_SMALL = 3
    GAP = 6
    GAP_LARGE = 10

    PROGRESS_HEIGHT = 7
    PROGRESS_CELLS = 14

    DEFAULT_W = 380
    DEFAULT_H = 195
    MIN_W = 210
    MIN_H = 115
    MAX_W = 900
    MAX_H = 1200

    RESIZE_GRIP = 6          # transparent ring the window owns, for edge drags
    GRIP_VISUAL = 16         # the visible corner handle


_scale = 1.0


def set_scale(value: float) -> None:
    global _scale
    _scale = max(0.75, min(3.0, float(value)))


def get_scale() -> float:
    return _scale


def px(value: float) -> int:
    """Design pixels -> device-independent pixels, snapped to whole pixels."""
    return max(1, round(value * _scale)) if value else 0


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
SYSTEM_FALLBACKS = ("Consolas", "Lucida Console", "Courier New")

# Two type roles give the panel its hierarchy:
#   BODY  - chunky pixel face with true lowercase (titles, task text)
#   LABEL - tight all-caps pixel face for the small tracked-out headings
# Any .ttf/.otf dropped in assets/fonts is registered; these names are simply
# preferred when present. All are OFL/CC0 -- none are Mojang assets.
BODY_PREFERRED = ("Pixelify Sans", "Pixel Operator", "Minecraftia", "Jersey 15", "VT323")
LABEL_PREFERRED = ("Silkscreen", "Press Start 2P", "Pixel Operator", "Pixelify Sans")

BODY = "body"
LABEL = "label"

_families: dict[str, str] = {}


def _pick(found: set[str], preferred: tuple[str, ...]) -> str | None:
    for name in preferred:
        for fam in found:
            if fam.lower().startswith(name.lower()):
                return fam
    return None


def load_fonts() -> dict[str, str]:
    """Register bundled pixel fonts and resolve the two type roles.

    Falls back to a system monospace face when ``assets/fonts`` is empty, so
    the app stays fully functional with no bundled typography at all.
    """
    global _families
    if _families:
        return _families

    found: set[str] = set()
    fonts_dir = asset("fonts")
    if fonts_dir.is_dir():
        for path in sorted(fonts_dir.iterdir()):
            if path.suffix.lower() not in (".ttf", ".otf"):
                continue
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid != -1:
                found.update(QFontDatabase.applicationFontFamilies(fid))

    system = "Monospace"
    available = set(QFontDatabase.families())
    for name in SYSTEM_FALLBACKS:
        if name in available:
            system = name
            break

    body = _pick(found, BODY_PREFERRED) or (sorted(found)[0] if found else system)
    label = _pick(found, LABEL_PREFERRED) or body
    _families = {BODY: body, LABEL: label}
    return _families


def family(role: str = BODY) -> str:
    return load_fonts().get(role, load_fonts()[BODY])


def set_families(body: str, label: str | None = None) -> None:
    """Override the resolved families (used by the font preview harness)."""
    global _families
    _families = {BODY: body, LABEL: label or body}


def font(
    size: int,
    bold: bool = False,
    letter_spacing: float = 0.0,
    role: str = BODY,
) -> QFont:
    f = QFont(family(role))
    f.setPixelSize(px(size))
    f.setBold(bold)
    f.setStyleStrategy(QFont.StyleStrategy(QFont.PreferAntialias | QFont.PreferQuality))
    if letter_spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px(letter_spacing))
    return f


def label_font(size: int, letter_spacing: float = 1.0) -> QFont:
    return font(size, letter_spacing=letter_spacing, role=LABEL)
