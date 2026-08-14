"""QuestPanel -- a Minecraft-inspired quest tracker overlay for Windows."""
from __future__ import annotations

import os
import sys

# Qt6 handles per-monitor DPI natively; PassThrough keeps our pixel-art
# metrics on exact integer boundaries instead of blurring at 125%/150%.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.application import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
