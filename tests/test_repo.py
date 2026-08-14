"""Repository / persistence tests. Run with: python -m pytest tests -q"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import Database  # noqa: E402
from app.database.repo import Repo  # noqa: E402
from app.services.settings import DEFAULTS, SettingsStore  # noqa: E402


@pytest.fixture()
def repo(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    yield Repo(db)
    db.close()


def test_seed_creates_sample_objective_once(repo: Repo):
    repo.seed_if_empty()
    repo.seed_if_empty()
    objectives = repo.list_objectives()
    assert len(objectives) == 1
    active = repo.active_objective()
    assert active is not None
    assert active.title == "Prepare for the Nether"
    assert active.total_count == 4
    assert active.done_count == 2
    assert active.progress == 0.5


def test_task_crud_and_toggle(repo: Repo):
    obj_id = repo.create_objective("Prepare for GATE")
    sec_id = repo.create_section(obj_id, "Study")
    task_id = repo.create_task(sec_id, "Solve PYQs", priority=2, icon="book")

    obj = repo.get_objective(obj_id)
    assert obj is not None and obj.total_count == 1
    task = obj.sections[0].tasks[0]
    assert (task.text, task.priority, task.icon, task.done) == ("Solve PYQs", 2, "book", False)

    assert repo.toggle_task(task_id) is True
    assert repo.get_objective(obj_id).sections[0].tasks[0].done is True
    assert repo.toggle_task(task_id) is False

    repo.update_task(task_id, "Solve graph problems", priority=3, icon="star")
    task = repo.get_objective(obj_id).sections[0].tasks[0]
    assert (task.text, task.priority, task.icon) == ("Solve graph problems", 3, "star")

    repo.delete_task(task_id)
    assert repo.get_objective(obj_id).total_count == 0


def test_completed_timestamp_is_cleared_on_uncomplete(repo: Repo):
    obj_id = repo.create_objective("O")
    sec_id = repo.create_section(obj_id, "S")
    task_id = repo.create_task(sec_id, "T")

    repo.set_task_done(task_id, True)
    assert repo.get_objective(obj_id).sections[0].tasks[0].completed_at is not None
    repo.set_task_done(task_id, False)
    assert repo.get_objective(obj_id).sections[0].tasks[0].completed_at is None


def test_reordering_is_dense_and_clamped(repo: Repo):
    obj_id = repo.create_objective("O")
    sec_id = repo.create_section(obj_id, "S")
    ids = [repo.create_task(sec_id, f"T{i}") for i in range(4)]

    def order():
        return [t.id for t in repo.get_objective(obj_id).sections[0].tasks]

    assert order() == ids

    repo.reorder_task(ids[3], -1)
    assert order() == [ids[0], ids[1], ids[3], ids[2]]

    repo.reorder_task(ids[0], -5)          # clamped, no change
    assert order() == [ids[0], ids[1], ids[3], ids[2]]

    repo.reorder_task(ids[0], 99)          # clamped to the end
    assert order() == [ids[1], ids[3], ids[2], ids[0]]

    positions = [t.position for t in repo.get_objective(obj_id).sections[0].tasks]
    assert positions == [0, 1, 2, 3]


def test_section_reorder_and_delete_cascades(repo: Repo):
    obj_id = repo.create_objective("O")
    a = repo.create_section(obj_id, "A")
    b = repo.create_section(obj_id, "B")
    repo.create_task(a, "task in A")

    repo.reorder_section(b, -1)
    assert [s.id for s in repo.get_objective(obj_id).sections] == [b, a]

    repo.delete_section(a)
    obj = repo.get_objective(obj_id)
    assert [s.id for s in obj.sections] == [b]
    assert obj.total_count == 0


def test_delete_objective_cascades_and_reassigns_active(repo: Repo):
    first = repo.create_objective("First")
    sec = repo.create_section(first, "S")
    repo.create_task(sec, "T")
    second = repo.create_objective("Second")

    assert repo.active_objective().id == second
    repo.delete_objective(second)
    active = repo.active_objective()
    assert active is not None and active.id == first

    repo.delete_objective(first)
    assert repo.active_objective() is None
    assert repo.db.query("SELECT * FROM tasks") == []


def test_move_task_between_sections(repo: Repo):
    obj_id = repo.create_objective("O")
    a = repo.create_section(obj_id, "A")
    b = repo.create_section(obj_id, "B")
    task_id = repo.create_task(a, "T")

    repo.move_task_to_section(task_id, b)
    obj = repo.get_objective(obj_id)
    assert obj.sections[0].total_count == 0
    assert obj.sections[1].tasks[0].id == task_id


def test_clear_completed_and_reset(repo: Repo):
    obj_id = repo.create_objective("O")
    sec = repo.create_section(obj_id, "S")
    done = repo.create_task(sec, "done")
    repo.create_task(sec, "pending")
    repo.set_task_done(done, True)

    assert repo.clear_completed(obj_id) == 1
    assert repo.get_objective(obj_id).total_count == 1

    other = repo.create_task(sec, "another")
    repo.set_task_done(other, True)
    repo.reset_objective(obj_id)
    assert repo.get_objective(obj_id).done_count == 0


def test_progress_of_empty_objective_is_zero(repo: Repo):
    obj_id = repo.create_objective("Empty")
    obj = repo.get_objective(obj_id)
    assert obj.progress == 0.0
    assert obj.is_complete is False


def test_is_complete_when_all_done(repo: Repo):
    obj_id = repo.create_objective("O")
    sec = repo.create_section(obj_id, "S")
    for i in range(3):
        repo.set_task_done(repo.create_task(sec, f"T{i}"), True)
    assert repo.get_objective(obj_id).is_complete is True


def test_settings_roundtrip_types_and_persistence(tmp_path: Path):
    db = Database(tmp_path / "s.db")
    store = SettingsStore(db)
    assert store.bool("always_on_top") is DEFAULTS["always_on_top"]

    store.set("always_on_top", False)
    store.set("opacity", 0.5)
    store.set("win_x", 421)
    store.set("hotkey", "Ctrl+Alt+P")
    db.close()

    db2 = Database(tmp_path / "s.db")
    reloaded = SettingsStore(db2)
    assert reloaded.bool("always_on_top") is False
    assert reloaded.float("opacity") == 0.5
    assert reloaded.int("win_x") == 421
    assert reloaded.str("hotkey") == "Ctrl+Alt+P"
    db2.close()
