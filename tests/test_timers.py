"""Task timer tests: parsing, persistence, migration and the clock service.

Run with: python -m pytest tests -q
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import theme  # noqa: E402
from app.database.db import Database  # noqa: E402
from app.database.repo import Repo  # noqa: E402
from app.services.settings import SettingsStore  # noqa: E402
from app.services.timers import TimerService  # noqa: E402
from app.utils.duration import format_clock, format_compact, parse_duration  # noqa: E402
from app.widgets.quest_panel import QuestPanelView  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    yield app


@pytest.fixture()
def repo(tmp_path: Path):
    db = Database(tmp_path / "timers.db")
    yield Repo(db)
    db.close()


@pytest.fixture()
def clock(monkeypatch):
    """A hand-cranked monotonic clock, so tests never sleep."""
    state = {"now": 1000.0}
    monkeypatch.setattr("app.services.timers.time.monotonic", lambda: state["now"])
    return state


# ----------------------------------------------------------------------
# Duration parsing
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,seconds",
    [
        ("21h", 21 * 3600),
        ("21 hours", 21 * 3600),
        ("1h30m", 5400),
        ("1h 30m", 5400),
        ("1h 30m 15s", 5415),
        ("90m", 5400),
        ("45s", 45),
        ("45", 45 * 60),          # a bare number means minutes
        ("2:30", 2 * 3600 + 30 * 60),
        ("1:05:30", 3930),
        ("0:00", 0),
    ],
)
def test_parse_duration_accepts_the_forms_people_type(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("bad", ["", "   ", "soon", "1x", "1:2:3:4", "h", "-5m"])
def test_parse_duration_rejects_nonsense_as_zero(bad):
    assert parse_duration(bad) == 0


def test_parse_duration_is_capped():
    assert parse_duration("99999h") == 999 * 3600


def test_format_clock_switches_to_hours_and_can_blink():
    assert format_clock(0) == "00:00"
    assert format_clock(65) == "01:05"
    assert format_clock(3725) == "1:02:05"
    assert format_clock(65, blink_off=True) == "01 05"


def test_format_compact_reads_like_the_input():
    assert format_compact(21 * 3600) == "21h"
    assert format_compact(5400) == "1h 30m"
    assert format_compact(45 * 60) == "45m"
    assert format_compact(0) == "-"


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------
def test_timer_fields_round_trip(repo: Repo):
    obj = repo.create_objective("Weekly Challenge")
    sec = repo.create_section(obj, "Target")
    task_id = repo.create_task(
        sec, "Coding (Learning)", priority=1, icon="book",
        timer_enabled=True, timer_target=21 * 3600,
    )

    task = repo.get_objective(obj).sections[0].tasks[0]
    assert task.timer_enabled is True
    assert task.timer_target == 21 * 3600
    assert task.timer_elapsed == 0
    assert task.timer_remaining == 21 * 3600
    assert task.timer_progress == 0.0

    repo.set_task_elapsed(task_id, 3600)
    task = repo.get_objective(obj).sections[0].tasks[0]
    assert task.timer_elapsed == 3600
    assert task.timer_progress == pytest.approx(1 / 21)
    assert task.timer_reached is False

    repo.set_task_elapsed(task_id, 21 * 3600)
    assert repo.get_objective(obj).sections[0].tasks[0].timer_reached is True

    repo.reset_task_timer(task_id)
    assert repo.task_elapsed(task_id) == 0


def test_tasks_default_to_no_timer(repo: Repo):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    repo.create_task(sec, "Bible Verse Reading")
    task = repo.get_objective(obj).sections[0].tasks[0]
    assert task.timer_enabled is False
    assert (task.timer_target, task.timer_elapsed) == (0, 0)
    assert task.timer_progress == 0.0


def test_update_task_leaves_the_timer_alone_when_not_asked(repo: Repo):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    task_id = repo.create_task(sec, "Exercise", timer_enabled=True, timer_target=3600)
    repo.set_task_elapsed(task_id, 120)

    repo.update_task(task_id, "Exercise Harder", priority=2)
    task = repo.get_objective(obj).sections[0].tasks[0]
    assert (task.text, task.timer_enabled, task.timer_target, task.timer_elapsed) == (
        "Exercise Harder", True, 3600, 120
    )

    repo.set_task_timer(task_id, False)
    assert repo.get_objective(obj).sections[0].tasks[0].timer_enabled is False
    # Turning the timer off keeps the hours already banked.
    assert repo.task_elapsed(task_id) == 120


def test_a_v1_database_gains_the_timer_columns(tmp_path: Path):
    """The upgrade path: a week-old database must open and keep its data."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE objectives (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            subtitle TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT, objective_id INTEGER NOT NULL,
            title TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
            collapsed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, section_id INTEGER NOT NULL,
            text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 0, icon TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0, completed_at TEXT
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES('schema_version', '1');
        INSERT INTO objectives(id, title, is_active) VALUES(1, 'Weekly Challenge', 1);
        INSERT INTO sections(id, objective_id, title) VALUES(1, 1, 'To do');
        INSERT INTO tasks(section_id, text, done, priority) VALUES(1, 'GATE Study', 1, 3);
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    repo = Repo(db)
    objective = repo.active_objective()
    assert objective is not None and objective.title == "Weekly Challenge"
    task = objective.sections[0].tasks[0]
    assert (task.text, task.done, task.priority) == ("GATE Study", True, 3)
    assert (task.timer_enabled, task.timer_target, task.timer_elapsed) == (False, 0, 0)

    version = db.query_one("SELECT value FROM meta WHERE key='schema_version'")
    assert version["value"] == "2"

    # And the migration is idempotent -- reopening must not fail.
    db.close()
    db2 = Database(path)
    assert Repo(db2).active_objective() is not None
    db2.close()


# ----------------------------------------------------------------------
# TimerService
# ----------------------------------------------------------------------
def test_start_pause_banks_elapsed_seconds(qapp, repo: Repo, clock):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    task_id = repo.create_task(sec, "Coding", timer_enabled=True, timer_target=3600)

    timers = TimerService(repo)
    timers.start(task_id, 0, 3600)
    assert timers.is_running(task_id) is True

    clock["now"] += 90
    assert timers.elapsed(task_id, 0) == 90

    assert timers.pause(task_id) == 90
    assert timers.is_running(task_id) is False
    assert repo.task_elapsed(task_id) == 90

    # Resuming continues from the banked total rather than restarting at zero.
    timers.start(task_id, 90, 3600)
    clock["now"] += 10
    assert timers.elapsed(task_id, 90) == 100
    timers.pause(task_id)
    assert repo.task_elapsed(task_id) == 100


def test_only_one_timer_runs_at_a_time(qapp, repo: Repo, clock):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    first = repo.create_task(sec, "Coding", timer_enabled=True)
    second = repo.create_task(sec, "GATE Study", timer_enabled=True)

    timers = TimerService(repo)
    timers.start(first, 0)
    clock["now"] += 60
    timers.start(second, 0)

    assert timers.running_ids() == [second]
    # The first task's minute was banked, not thrown away.
    assert repo.task_elapsed(first) == 60


def test_toggle_and_reset(qapp, repo: Repo, clock):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    task_id = repo.create_task(sec, "Exercise", timer_enabled=True, timer_target=600)

    timers = TimerService(repo)
    assert timers.toggle(task_id, 0, 600) is True
    clock["now"] += 30
    assert timers.toggle(task_id, 0, 600) is False
    assert repo.task_elapsed(task_id) == 30

    timers.reset(task_id)
    assert repo.task_elapsed(task_id) == 0
    assert timers.is_running(task_id) is False


def test_target_reached_fires_once(qapp, repo: Repo, clock):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    task_id = repo.create_task(sec, "Stretch", timer_enabled=True, timer_target=10)

    timers = TimerService(repo)
    fired: list[int] = []
    timers.target_reached.connect(fired.append)

    timers.start(task_id, 0, 10)
    clock["now"] += 4
    timers._on_tick()
    assert fired == []

    clock["now"] += 8
    timers._on_tick()
    timers._on_tick()
    assert fired == [task_id]


def test_shutdown_banks_running_time(qapp, repo: Repo, clock):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    task_id = repo.create_task(sec, "Editing", timer_enabled=True)

    timers = TimerService(repo)
    timers.start(task_id, 0)
    clock["now"] += 45
    timers.shutdown()
    assert repo.task_elapsed(task_id) == 45
    assert timers.running_ids() == []


def test_forget_drops_a_deleted_task_without_writing_it_back(qapp, repo: Repo, clock):
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    task_id = repo.create_task(sec, "Doomed", timer_enabled=True)

    timers = TimerService(repo)
    timers.start(task_id, 0)
    clock["now"] += 20
    timers.forget(task_id)
    repo.delete_task(task_id)

    assert timers.running_ids() == []
    timers.shutdown()          # must not resurrect a row for the deleted task
    assert repo.get_objective(obj).total_count == 0


# ----------------------------------------------------------------------
# The row keeps ticking across a rebuild
# ----------------------------------------------------------------------
def _timer_panel(tmp_path: Path, target: int = 21 * 3600):
    db = Database(tmp_path / "panel.db")
    repo = Repo(db)
    obj = repo.create_objective("Weekly Challenge")
    sec = repo.create_section(obj, "Target")
    task_id = repo.create_task(
        sec, "Coding (Learning)", timer_enabled=True, timer_target=target
    )
    settings = SettingsStore(db)
    settings.set("animations_enabled", False)
    view = QuestPanelView(repo, settings)
    view.resize(380, 220)
    view.reload()
    # Without a show() the layout never runs, every row stays 100px wide, and
    # the chip correctly reports that it has no room to draw itself.
    view.show()
    QApplication.processEvents()
    return db, repo, settings, view, task_id


def test_clicking_the_chip_runs_the_clock_and_leaves_the_task_alone(qapp, tmp_path, clock):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from app.ui.panel_controller import PanelController

    db, repo, settings, view, task_id = _timer_panel(tmp_path)
    PanelController(view, repo, settings, parent=view)
    row = view._task_rows[task_id]

    chip = row._chip_rect()
    assert chip is not None
    QTest.mouseClick(row, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, chip.center())

    assert view.timers.is_running(task_id) is True
    assert repo.get_objective(view.objective.id).sections[0].tasks[0].done is False

    clock["now"] += 5
    QTest.mouseClick(row, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, chip.center())
    assert view.timers.is_running(task_id) is False
    assert repo.task_elapsed(task_id) == 5

    view.timers.shutdown()
    view.deleteLater()
    db.close()


def test_clicking_the_row_ticks_the_task_and_leaves_the_clock_alone(qapp, tmp_path, clock):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from app.ui.panel_controller import PanelController

    db, repo, settings, view, task_id = _timer_panel(tmp_path)
    PanelController(view, repo, settings, parent=view)
    row = view._task_rows[task_id]

    QTest.mouseClick(row, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(6, row.height() // 2))

    assert repo.get_objective(view.objective.id).sections[0].tasks[0].done is True
    assert view.timers.is_running(task_id) is False

    view.deleteLater()
    db.close()


def test_completing_a_task_stops_its_running_clock(qapp, tmp_path, clock):
    from app.ui.panel_controller import PanelController

    db, repo, settings, view, task_id = _timer_panel(tmp_path)
    controller = PanelController(view, repo, settings, parent=view)

    controller.toggle_timer(task_id)
    assert view.timers.is_running(task_id) is True

    clock["now"] += 300
    controller.toggle_task(task_id)

    assert view.timers.is_running(task_id) is False
    assert repo.task_elapsed(task_id) == 300

    view.deleteLater()
    db.close()


def test_a_task_without_a_timer_shows_no_chip(qapp, tmp_path):
    db = Database(tmp_path / "plain.db")
    repo = Repo(db)
    obj = repo.create_objective("O")
    sec = repo.create_section(obj, "S")
    task_id = repo.create_task(sec, "Praying")
    settings = SettingsStore(db)
    settings.set("animations_enabled", False)

    view = QuestPanelView(repo, settings)
    view.resize(380, 220)
    view.reload()

    row = view._task_rows[task_id]
    assert row._chip_rect() is None
    assert row.toolTip() == ""

    view.deleteLater()
    db.close()


def test_running_timer_survives_a_panel_reload(qapp, tmp_path: Path, clock):
    db = Database(tmp_path / "panel.db")
    repo = Repo(db)
    obj = repo.create_objective("Weekly Challenge")
    sec = repo.create_section(obj, "Target")
    task_id = repo.create_task(
        sec, "Coding (Learning)", timer_enabled=True, timer_target=21 * 3600
    )
    settings = SettingsStore(db)

    view = QuestPanelView(repo, settings)
    view.resize(380, 220)
    view.reload()

    view.timers.start(task_id, 0, 21 * 3600)
    clock["now"] += 120
    view.reload()

    row = view._task_rows[task_id]
    assert row.timer_running is True
    assert row._elapsed == 120
    assert "02:00" in row._timer_text() or "02 00" in row._timer_text()

    view.timers.shutdown()
    view.deleteLater()
    db.close()


# ----------------------------------------------------------------------
# Deleting the rows out from under a running clock
# ----------------------------------------------------------------------
def _controller_panel(tmp_path: Path, monkeypatch):
    """A panel wired to a controller, with every confirm dialog auto-accepted."""
    from app.ui import panel_controller as pc

    monkeypatch.setattr(pc, "confirm", lambda *a, **k: True)

    db = Database(tmp_path / "delete.db")
    repo = Repo(db)
    settings = SettingsStore(db)
    obj = repo.create_objective("Weekly Challenge")
    sec = repo.create_section(obj, "Target")
    task_id = repo.create_task(
        sec, "Coding (Learning)", timer_enabled=True, timer_target=21 * 3600
    )
    view = QuestPanelView(repo, settings)
    view.resize(380, 220)
    view.reload()
    controller = pc.PanelController(view, repo, settings, parent=view)
    return db, repo, view, controller, obj, sec, task_id


def test_deleting_a_section_stops_the_clock_inside_it(qapp, tmp_path, monkeypatch, clock):
    db, repo, view, controller, _obj, sec, task_id = _controller_panel(tmp_path, monkeypatch)

    view.timers.start(task_id, 0, 21 * 3600)
    clock["now"] += 30
    controller.delete_section(sec)

    # The row is gone, so the clock must be gone with it -- otherwise it keeps
    # ticking invisibly and the next flush writes to a deleted row.
    assert view.timers.running_ids() == []
    assert view.timers.is_running(task_id) is False

    view.timers.shutdown()
    view.deleteLater()
    db.close()


def test_deleting_an_objective_stops_every_clock_under_it(qapp, tmp_path, monkeypatch, clock):
    db, repo, view, controller, obj, _sec, task_id = _controller_panel(tmp_path, monkeypatch)

    view.timers.start(task_id, 0, 21 * 3600)
    clock["now"] += 30
    controller.delete_objective()

    assert view.timers.running_ids() == []
    assert repo.get_objective(obj) is None

    view.timers.shutdown()
    view.deleteLater()
    db.close()


def test_clearing_completed_stops_the_clocks_it_deletes(qapp, tmp_path, monkeypatch, clock):
    db, repo, view, controller, obj, sec, task_id = _controller_panel(tmp_path, monkeypatch)
    keeper = repo.create_task(sec, "GATE Studies", timer_enabled=True, timer_target=42 * 3600)
    view.reload()

    # A done task whose clock is somehow still running is exactly the case
    # that used to leak, so drive it straight into that state.
    repo.set_task_done(task_id, True)
    view.reload()
    view.timers.start(task_id, 0, 21 * 3600)
    clock["now"] += 30

    controller._clear_completed()

    assert view.timers.is_running(task_id) is False
    # The surviving task's own clock is untouched.
    view.timers.start(keeper, 0, 42 * 3600)
    assert view.timers.is_running(keeper) is True

    view.timers.shutdown()
    view.deleteLater()
    db.close()


def test_switching_objective_banks_the_running_clock(qapp, tmp_path, monkeypatch, clock):
    db, repo, view, controller, _obj, _sec, task_id = _controller_panel(tmp_path, monkeypatch)
    other = repo.create_objective("Next Week")
    repo.create_section(other, "Target")

    view.timers.start(task_id, 0, 21 * 3600)
    clock["now"] += 300
    controller.switch_objective(other)

    # Time already worked is kept; the clock does not run on where you cannot see it.
    assert view.timers.running_ids() == []
    assert repo.task_elapsed(task_id) == 300

    view.timers.shutdown()
    view.deleteLater()
    db.close()


def test_hitting_the_target_announces_the_task_and_its_goal(qapp, tmp_path, monkeypatch, clock):
    """The controller hands the notification layer what it needs to word a toast."""
    db, repo, view, controller, _obj, _sec, task_id = _controller_panel(tmp_path, monkeypatch)

    announced: list[tuple[str, int]] = []
    controller.timer_target_reached.connect(lambda text, target: announced.append((text, target)))

    # A three-second goal, so one tick of the hand-cranked clock clears it.
    repo.set_task_timer(task_id, True, 3)
    view.reload()
    view.timers.start(task_id, 0, 3)
    clock["now"] += 5
    view.timers._on_tick()

    assert announced == [("Coding (Learning)", 3)]

    # And it stays a one-shot: further ticks past the goal say nothing more.
    clock["now"] += 5
    view.timers._on_tick()
    assert len(announced) == 1

    view.timers.shutdown()
    view.deleteLater()
    db.close()
