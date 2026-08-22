"""Headless-ish smoke test: boot the real app, poke it, screenshot, exit.

Run with:  python tests/smoke_run.py
It creates the window for real (so painting code executes), grabs a PNG so
the layout can be eyeballed, then shuts everything down.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.application import QuestPanelApp  # noqa: E402
from app.core import paths  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="questpanel-smoke-"))
    paths.database_path = lambda: tmp / "smoke.db"  # type: ignore[assignment]

    # This harness boots the real app, which creates sections, ticks tasks and
    # saves window geometry. All of that has to land in the throwaway database
    # above -- so prove the redirect actually took before anything opens it.
    # (It silently did not once: db.py had imported the name directly, so this
    # patch was ignored and the run edited the user's live to-do list.)
    from app.database.db import Database

    probe = Database()
    resolved = probe.path
    probe.close()
    if resolved != tmp / "smoke.db":
        raise SystemExit(
            f"refusing to run: the app would open {resolved}, not the temp database.\n"
            "Something rebound paths.database_path -- fix that before running this."
        )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    ctrl = QuestPanelApp(app)
    ctrl.overlay.show_overlay(animate=False)

    out = ROOT / "build" / "smoke.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []

    def check(condition: bool, label: str) -> None:
        print(f"{'ok  ' if condition else 'FAIL'} {label}", flush=True)
        if not condition:
            failures.append(label)

    def capture() -> None:
        ok = ctrl.overlay.grab().save(str(out))
        geom = ctrl.overlay.geometry()
        print(f"geometry={geom.x()},{geom.y()} {geom.width()}x{geom.height()}", flush=True)
        print(f"hotkey registered={ctrl.hotkey.is_registered} "
              f"seq={ctrl.hotkey.sequence!r}", flush=True)
        check(ctrl.overlay.isVisible(), "overlay visible after show")
        check(ctrl.tray.icon.isVisible(), "tray icon visible")
        check(ctrl.hotkey.is_registered, "global hotkey registered")
        check(ok, f"screenshot written to {out}")

        ctrl.overlay.hide_overlay(animate=False)
        check(not ctrl.overlay.isVisible(), "instant hide")
        ctrl.toggle()
        check(ctrl.overlay.isVisible(), "toggle shows")

    def after_animated_hide() -> None:
        # toggle() fades out over ~130ms before actually hiding.
        ctrl.toggle()
        QTimer.singleShot(400, finish)

    def finish() -> None:
        check(not ctrl.overlay.isVisible(), "animated toggle hides")
        # Geometry must survive a round trip through the database.
        ctrl.overlay.move(300, 180)
        ctrl.overlay.resize(360, 240)
        ctrl.overlay.save_geometry()
        check(ctrl.settings.int("win_x") == 300 and ctrl.settings.int("win_w") == 360,
              "geometry persisted to settings")
        print("FAILURES:" + (", ".join(failures) if failures else " none"), flush=True)
        ctrl.quit()
        app.exit(1 if failures else 0)

    QTimer.singleShot(600, capture)
    QTimer.singleShot(900, after_animated_hide)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
