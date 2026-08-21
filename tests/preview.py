"""Render every surface to build/preview-*.png for visual inspection.

    python tests/preview.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import theme  # noqa: E402
from app.database.db import Database  # noqa: E402
from app.database.repo import Repo  # noqa: E402
from app.services.settings import SettingsStore  # noqa: E402
from app.ui.dialogs import TaskDialog, TimerDialog  # noqa: E402
from app.ui.overlay import OverlayWindow  # noqa: E402
from app.ui.settings_window import SettingsWindow  # noqa: E402
from app.widgets.quest_panel import QuestPanelView  # noqa: E402

OUT = ROOT / "build"


def build_data(db: Database) -> Repo:
    repo = Repo(db)
    repo.seed_if_empty()
    obj = repo.active_objective()
    assert obj is not None
    study = repo.create_section(obj.id, "Study")
    repo.set_task_done(repo.create_task(study, "Complete OS revision", 1, "book"), True)
    repo.create_task(study, "Solve graph problems", 3, "star")
    coding = repo.create_section(obj.id, "Coding")
    repo.create_task(coding, "Build dashboard", 2, "gear")

    # Timer rows: a long goal part-way through, a short one already met, and
    # a goal-less stopwatch.
    target = repo.create_section(obj.id, "Target")
    long_run = repo.create_task(target, "Coding (Learning)", 1, "book",
                                timer_enabled=True, timer_target=21 * 3600)
    repo.set_task_elapsed(long_run, 7 * 3600 + 26 * 60)
    met = repo.create_task(target, "Exercise", 2, "sword",
                           timer_enabled=True, timer_target=45 * 60)
    repo.set_task_elapsed(met, 47 * 60)
    stopwatch = repo.create_task(target, "Editing", 0, "star", timer_enabled=True)
    repo.set_task_elapsed(stopwatch, 95)
    return repo


def shot(widget, name: str, backdrop: bool = True) -> None:
    """Grab the widget, optionally over a backdrop.

    The overlay window is transparent, so a bare grab would render the card
    gaps as black. Compositing over a mid-tone approximates how it actually
    looks sitting on a desktop.
    """
    pm = widget.grab()
    if backdrop:
        canvas = QPixmap(pm.width() + 24, pm.height() + 24)
        canvas.fill(QColor(0x3A, 0x14, 0x14))       # nether-ish, like the reference
        p = QPainter(canvas)
        p.drawPixmap(12, 12, pm)
        p.end()
        pm = canvas
    pm.save(str(OUT / f"preview-{name}.png"))
    print(f"  preview-{name}.png  ({widget.width()}x{widget.height()})")


def main() -> int:
    app = QApplication(sys.argv)
    theme.load_fonts()
    OUT.mkdir(parents=True, exist_ok=True)

    # A hung harness leaves a stray process behind holding a window on screen,
    # so guarantee an exit no matter what the timer chain does.
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: (print("  [watchdog] forcing exit"),
                                      sys.stdout.flush(), os._exit(2)))
    watchdog.start(30_000)

    tmp = Path(tempfile.mkdtemp(prefix="qp-preview-"))
    db = Database(tmp / "preview.db")
    repo = build_data(db)
    settings = SettingsStore(db)
    settings.set("win_x", 200)
    settings.set("win_y", 120)
    # Rows fade and slide in on a stagger; a single processEvents() grabs them
    # mid-entrance, i.e. invisible. Stills want the settled state.
    settings.set("animations_enabled", False)

    # 1. Default overlay -------------------------------------------------
    overlay = OverlayWindow(settings)
    panel = QuestPanelView(repo, settings)
    overlay.set_content(panel)
    overlay.resize(380, 470)
    panel.reload()
    # One clock left running, so the preview shows both timer states.
    running = next(
        t for s in panel.objective.sections for t in s.tasks
        if t.timer_enabled and t.timer_target and not t.timer_reached
    )
    panel.timers.start(running.id, running.timer_elapsed, running.timer_target)
    overlay.show()
    app.processEvents()
    shot(overlay, "overlay-default")

    # 2. Compact mode ----------------------------------------------------
    settings.set("compact_mode", True)
    panel.apply_settings()
    app.processEvents()
    shot(overlay, "overlay-compact")
    settings.set("compact_mode", False)
    panel.apply_settings()

    # 3. Celebration -----------------------------------------------------
    panel.celebrate()
    app.processEvents()
    QTimer.singleShot(300, lambda: (shot(panel, "celebration", backdrop=False), step4()))

    def step4() -> None:
        # 4. Settings window ---------------------------------------------
        win = SettingsWindow(settings, overlay)
        win.show()
        app.processEvents()
        shot(win, "settings", backdrop=False)
        win.close()

        # 5. Task dialog --------------------------------------------------
        dialog = TaskDialog("Edit Task", "Solve graph problems", 3, "star",
                            True, 21 * 3600)
        dialog.adjustSize()
        dialog.show()
        app.processEvents()
        shot(dialog, "dialog-task", backdrop=False)
        dialog.close()

        # 5b. Timer dialog -------------------------------------------------
        timer_dialog = TimerDialog("Coding (Learning)", True, 21 * 3600,
                                   7 * 3600 + 26 * 60)
        timer_dialog.adjustSize()
        timer_dialog.show()
        app.processEvents()
        shot(timer_dialog, "dialog-timer", backdrop=False)
        timer_dialog.close()

        # 6. 150% UI scale -- rendered inside a real overlay, as shipped ---
        theme.set_scale(1.5)
        scaled = OverlayWindow(settings)
        scaled_panel = QuestPanelView(repo, settings)
        scaled.set_content(scaled_panel)
        scaled.resize(570, 700)
        scaled_panel.reload()
        scaled.show()
        app.processEvents()
        shot(scaled, "scale-150")
        scaled.close()
        theme.set_scale(1.0)

        overlay.hide()
        db.close()
        # Qt keeps the loop alive for the hidden tool windows; this is a dev
        # harness, so leave decisively.
        sys.stdout.flush()
        os._exit(0)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
