"""Drifting cherry-blossom petals around the overlay.

A transparent, click-through layer sitting above the cards. Petals bloom in
with a short scale-up, drift down while swaying, and fade out at the end of
their life.

Kept cheap on purpose: a fixed particle budget, one timer, integer-snapped
pixel drawing, and the timer stops dead whenever the layer is hidden or the
setting is off -- an idle overlay must not burn CPU.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QRegion
from PySide6.QtWidgets import QWidget

from ..core.theme import px

# 20fps. Every frame costs a full recomposite of a translucent always-on-top
# window -- that, not the drawing, is what this effect actually pays for, so
# frame rate is the only lever that meaningfully moves the cost. Slow drifting
# petals still read as smooth here.
FRAME_MS = 50
MAX_PETALS = 10
DIRTY_PAD = 2                 # slack around a petal's box, in device pixels

# Pixel blossoms, drawn on their own tiny grids. Three silhouettes so the
# field does not read as one repeated stamp.
SHAPES = (
    (
        ".X.X.",
        "XXXXX",
        "XXoXX",
        "XXXXX",
        ".X.X.",
    ),
    (
        ".XX.",
        "XXXX",
        "XXoX",
        ".XX.",
    ),
    (
        "..X..",
        ".XXX.",
        "XXoXX",
        ".XXX.",
        "..X..",
    ),
)

# Sakura palette: (petal, highlight)
PALETTES = (
    (QColor(0xFF, 0xB7, 0xC5), QColor(0xFF, 0xF0, 0xF5)),
    (QColor(0xFF, 0xD9, 0xE1), QColor(0xFF, 0xFF, 0xFF)),
    (QColor(0xF7, 0x9E, 0xB6), QColor(0xFF, 0xE4, 0xEC)),
    (QColor(0xFF, 0xC8, 0xDD), QColor(0xFF, 0xF5, 0xFA)),
)


@dataclass
class Petal:
    x: float
    y: float
    vx: float
    vy: float
    size: int
    shape: int
    palette: int
    age: float = 0.0
    life: float = 6.0
    sway: float = 0.0
    sway_speed: float = 1.0
    spin: float = 0.0
    field_unused: int = field(default=0, repr=False)

    @property
    def bloom(self) -> float:
        """0..1 scale-up over the first 250ms, so petals pop into existence."""
        return min(1.0, self.age / 0.25)

    @property
    def alpha(self) -> float:
        fade_in = min(1.0, self.age / 0.4)
        remaining = self.life - self.age
        fade_out = min(1.0, max(0.0, remaining / 1.2))
        return fade_in * fade_out


class BlossomLayer(QWidget):
    """Click-through petal field drawn over the panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._petals: list[Petal] = []
        self._rng = random.Random()
        self._enabled = False
        # Petals cross the task text, so they are deliberately held back --
        # decoration must never cost legibility.
        self._intensity = 0.7

        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            self.show()
            self.raise_()
            self._seed()
            self._timer.start()
        else:
            self._timer.stop()
            self._petals.clear()
            self.hide()
        self.update()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _budget(self) -> int:
        """Scale the particle count with the window so small overlays are not
        swamped and large ones do not look empty."""
        area = max(1, self.width() * self.height())
        scaled = int(MAX_PETALS * min(1.0, area / (420.0 * 260.0)))
        return max(4, scaled)

    def _seed(self) -> None:
        self._petals = [self._spawn(initial=True) for _ in range(self._budget())]

    def _spawn(self, initial: bool = False) -> Petal:
        w = max(1, self.width())
        h = max(1, self.height())
        size = self._rng.choice((3, 3, 4, 4, 5))
        return Petal(
            x=self._rng.uniform(-10, w + 10),
            y=self._rng.uniform(-20, h) if initial else self._rng.uniform(-30, -8),
            vx=self._rng.uniform(-9.0, 5.0),
            vy=self._rng.uniform(10.0, 26.0),
            size=size,
            shape=self._rng.randrange(len(SHAPES)),
            palette=self._rng.randrange(len(PALETTES)),
            life=self._rng.uniform(4.5, 9.0),
            age=self._rng.uniform(0.0, 2.0) if initial else 0.0,
            sway=self._rng.uniform(0.0, math.tau),
            sway_speed=self._rng.uniform(0.6, 1.6),
            spin=self._rng.uniform(0.0, math.tau),
        )

    # ------------------------------------------------------------------
    def _petal_rect(self, petal: Petal) -> QRect:
        """Generous bounding box for one petal, in widget coordinates."""
        grid = SHAPES[petal.shape]
        scale = max(1, int(round(px(petal.size))))
        w = len(grid[0]) * scale + DIRTY_PAD * 2
        h = len(grid) * scale + DIRTY_PAD * 2
        return QRect(int(petal.x) - DIRTY_PAD, int(petal.y) - DIRTY_PAD, w, h)

    def _tick(self) -> None:
        if not self.isVisible() or not self._enabled:
            self._timer.stop()
            return

        dt = FRAME_MS / 1000.0
        h = self.height()
        budget = self._budget()

        # Repaint only where petals were and where they now are. Repainting the
        # whole widget forces a full recomposite of the translucent window every
        # frame, which cost several percent CPU while merely idling.
        dirty: list[QRect] = [self._petal_rect(p) for p in self._petals]

        for petal in self._petals:
            petal.age += dt
            petal.sway += petal.sway_speed * dt
            petal.spin += dt * 1.4
            # Horizontal sway is what sells 'falling petal' over 'falling dot'.
            petal.x += (petal.vx + math.sin(petal.sway) * 14.0) * dt
            petal.y += petal.vy * dt

        self._petals = [
            p for p in self._petals
            if p.age < p.life and p.y < h + 24
        ]
        while len(self._petals) < budget:
            self._petals.append(self._spawn())
        # Shrinking the window can leave us over budget.
        if len(self._petals) > budget:
            del self._petals[budget:]

        dirty.extend(self._petal_rect(p) for p in self._petals)
        region = QRegion()
        for rect in dirty:
            region += rect
        self.update(region)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._enabled or not self._petals:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        region = event.region()

        for petal in self._petals:
            if not region.intersects(self._petal_rect(petal)):
                continue
            grid = SHAPES[petal.shape]
            base, highlight = PALETTES[petal.palette]
            scale = max(1, int(round(px(petal.size) * petal.bloom)))
            if scale < 1:
                continue

            # Squash horizontally on a slow cycle: a cheap stand-in for the
            # petal turning over as it falls.
            squash = abs(math.cos(petal.spin))
            x_scale = max(1, int(round(scale * (0.35 + 0.65 * squash))))

            alpha = petal.alpha * self._intensity
            if alpha <= 0.02:
                continue
            body = QColor(base)
            body.setAlphaF(min(1.0, alpha * 0.85))
            spot = QColor(highlight)
            spot.setAlphaF(min(1.0, alpha))

            ox = int(petal.x)
            oy = int(petal.y)
            for row, line in enumerate(grid):
                for col, ch in enumerate(line):
                    if ch == ".":
                        continue
                    p.fillRect(
                        ox + col * x_scale,
                        oy + row * scale,
                        x_scale,
                        scale,
                        spot if ch == "o" else body,
                    )
        p.end()

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._enabled and not self._timer.isActive():
            if not self._petals:
                self._seed()
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        # No point animating something nobody can see.
        self._timer.stop()
        super().hideEvent(event)
