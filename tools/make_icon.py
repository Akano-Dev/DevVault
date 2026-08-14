"""Generate build/questpanel.ico from the runtime-drawn app icon.

Run once before packaging:  python tools/make_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.icons import app_icon  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    out = ROOT / "build" / "questpanel.ico"
    out.parent.mkdir(parents=True, exist_ok=True)

    icon = app_icon()
    sizes = [16, 24, 32, 48, 64, 128, 256]
    # QIcon can't write .ico directly; save the largest pixmap and let Qt's
    # ICO handler build the multi-size file from the icon's pixmaps.
    pixmaps = [icon.pixmap(s, s) for s in sizes]
    ok = pixmaps[-1].save(str(out), "ICO")
    print(f"{'wrote' if ok else 'FAILED to write'} {out}")
    del app
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
