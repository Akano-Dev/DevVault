"""CRUD for objectives, sections and tasks.

Ordering is stored as a dense ``position`` column per parent; the reorder
helpers renumber siblings so positions never drift.
"""
from __future__ import annotations

from ..models.entities import Objective, Section, Task
from .db import Database

SEED_OBJECTIVE = {
    "title": "Prepare for the Nether",
    "subtitle": "",
    "sections": [
        (
            "Getting Ready",
            [
                ("Get Tools and Items", True, 0, "pickaxe"),
                ("Build Nether Portal", True, 0, "flame"),
                ("Get Full Diamond Armor", False, 2, "sword"),
                ("Enchant All Gear", False, 1, "book"),
            ],
        )
    ],
}


class Repo:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Objectives
    # ------------------------------------------------------------------
    def list_objectives(self) -> list[Objective]:
        rows = self.db.query("SELECT * FROM objectives ORDER BY position, id")
        return [self._objective_from_row(r, with_children=False) for r in rows]

    def get_objective(self, objective_id: int) -> Objective | None:
        row = self.db.query_one("SELECT * FROM objectives WHERE id=?", (objective_id,))
        if row is None:
            return None
        return self._objective_from_row(row, with_children=True)

    def active_objective(self) -> Objective | None:
        row = self.db.query_one(
            "SELECT * FROM objectives WHERE is_active=1 ORDER BY position, id LIMIT 1"
        )
        if row is None:
            row = self.db.query_one("SELECT * FROM objectives ORDER BY position, id LIMIT 1")
        if row is None:
            return None
        return self._objective_from_row(row, with_children=True)

    def set_active_objective(self, objective_id: int) -> None:
        self.db.execute("UPDATE objectives SET is_active=0 WHERE is_active=1")
        self.db.execute("UPDATE objectives SET is_active=1 WHERE id=?", (objective_id,))

    def create_objective(self, title: str, subtitle: str = "", make_active: bool = True) -> int:
        pos = self._next_position("objectives", None, None)
        cur = self.db.execute(
            "INSERT INTO objectives(title, subtitle, position) VALUES(?, ?, ?)",
            (title.strip() or "Untitled Objective", subtitle.strip(), pos),
        )
        new_id = int(cur.lastrowid)
        if make_active:
            self.set_active_objective(new_id)
        return new_id

    def update_objective(self, objective_id: int, title: str, subtitle: str = "") -> None:
        self.db.execute(
            "UPDATE objectives SET title=?, subtitle=? WHERE id=?",
            (title.strip() or "Untitled Objective", subtitle.strip(), objective_id),
        )

    def delete_objective(self, objective_id: int) -> None:
        was_active = self.db.query_one(
            "SELECT is_active FROM objectives WHERE id=?", (objective_id,)
        )
        self.db.execute("DELETE FROM objectives WHERE id=?", (objective_id,))
        if was_active and was_active["is_active"]:
            nxt = self.db.query_one("SELECT id FROM objectives ORDER BY position, id LIMIT 1")
            if nxt:
                self.set_active_objective(int(nxt["id"]))

    def reorder_objective(self, objective_id: int, delta: int) -> None:
        self._reorder("objectives", None, None, objective_id, delta)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def create_section(self, objective_id: int, title: str) -> int:
        pos = self._next_position("sections", "objective_id", objective_id)
        cur = self.db.execute(
            "INSERT INTO sections(objective_id, title, position) VALUES(?, ?, ?)",
            (objective_id, title.strip() or "New Section", pos),
        )
        return int(cur.lastrowid)

    def rename_section(self, section_id: int, title: str) -> None:
        self.db.execute(
            "UPDATE sections SET title=? WHERE id=?",
            (title.strip() or "New Section", section_id),
        )

    def delete_section(self, section_id: int) -> None:
        self.db.execute("DELETE FROM sections WHERE id=?", (section_id,))

    def set_section_collapsed(self, section_id: int, collapsed: bool) -> None:
        self.db.execute(
            "UPDATE sections SET collapsed=? WHERE id=?", (1 if collapsed else 0, section_id)
        )

    def reorder_section(self, section_id: int, delta: int) -> None:
        row = self.db.query_one("SELECT objective_id FROM sections WHERE id=?", (section_id,))
        if row is None:
            return
        self._reorder("sections", "objective_id", int(row["objective_id"]), section_id, delta)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def create_task(
        self, section_id: int, text: str, priority: int = 0, icon: str = ""
    ) -> int:
        pos = self._next_position("tasks", "section_id", section_id)
        cur = self.db.execute(
            "INSERT INTO tasks(section_id, text, priority, icon, position) VALUES(?, ?, ?, ?, ?)",
            (section_id, text.strip() or "New Task", int(priority), icon, pos),
        )
        return int(cur.lastrowid)

    def update_task(
        self, task_id: int, text: str, priority: int | None = None, icon: str | None = None
    ) -> None:
        sets = ["text=?"]
        params: list = [text.strip() or "New Task"]
        if priority is not None:
            sets.append("priority=?")
            params.append(int(priority))
        if icon is not None:
            sets.append("icon=?")
            params.append(icon)
        params.append(task_id)
        self.db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", tuple(params))

    def set_task_done(self, task_id: int, done: bool) -> None:
        self.db.execute(
            "UPDATE tasks SET done=?, completed_at=CASE WHEN ? THEN datetime('now') END "
            "WHERE id=?",
            (1 if done else 0, 1 if done else 0, task_id),
        )

    def toggle_task(self, task_id: int) -> bool:
        row = self.db.query_one("SELECT done FROM tasks WHERE id=?", (task_id,))
        if row is None:
            return False
        new_state = not bool(row["done"])
        self.set_task_done(task_id, new_state)
        return new_state

    def delete_task(self, task_id: int) -> None:
        self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def move_task_to_section(self, task_id: int, section_id: int) -> None:
        pos = self._next_position("tasks", "section_id", section_id)
        self.db.execute(
            "UPDATE tasks SET section_id=?, position=? WHERE id=?", (section_id, pos, task_id)
        )

    def reorder_task(self, task_id: int, delta: int) -> None:
        row = self.db.query_one("SELECT section_id FROM tasks WHERE id=?", (task_id,))
        if row is None:
            return
        self._reorder("tasks", "section_id", int(row["section_id"]), task_id, delta)

    def clear_completed(self, objective_id: int) -> int:
        cur = self.db.execute(
            "DELETE FROM tasks WHERE done=1 AND section_id IN "
            "(SELECT id FROM sections WHERE objective_id=?)",
            (objective_id,),
        )
        return cur.rowcount

    def reset_objective(self, objective_id: int) -> None:
        self.db.execute(
            "UPDATE tasks SET done=0, completed_at=NULL WHERE section_id IN "
            "(SELECT id FROM sections WHERE objective_id=?)",
            (objective_id,),
        )

    # ------------------------------------------------------------------
    # Ordering helpers
    # ------------------------------------------------------------------
    def _next_position(self, table: str, parent_col: str | None, parent_id: int | None) -> int:
        if parent_col:
            row = self.db.query_one(
                f"SELECT COALESCE(MAX(position), -1) AS m FROM {table} WHERE {parent_col}=?",
                (parent_id,),
            )
        else:
            row = self.db.query_one(f"SELECT COALESCE(MAX(position), -1) AS m FROM {table}")
        return int(row["m"]) + 1 if row else 0

    def _reorder(
        self,
        table: str,
        parent_col: str | None,
        parent_id: int | None,
        row_id: int,
        delta: int,
    ) -> None:
        """Move a row up/down among its siblings and renumber densely."""
        if parent_col:
            rows = self.db.query(
                f"SELECT id FROM {table} WHERE {parent_col}=? ORDER BY position, id",
                (parent_id,),
            )
        else:
            rows = self.db.query(f"SELECT id FROM {table} ORDER BY position, id")
        ids = [int(r["id"]) for r in rows]
        if row_id not in ids:
            return
        i = ids.index(row_id)
        j = max(0, min(len(ids) - 1, i + delta))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        for pos, rid in enumerate(ids):
            self.db.execute(f"UPDATE {table} SET position=? WHERE id=?", (pos, rid))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def _objective_from_row(self, row, with_children: bool) -> Objective:
        obj = Objective(
            id=int(row["id"]),
            title=row["title"],
            subtitle=row["subtitle"],
            position=int(row["position"]),
            is_active=bool(row["is_active"]),
        )
        if with_children:
            obj.sections = self._sections_for(obj.id)
        return obj

    def _sections_for(self, objective_id: int) -> list[Section]:
        rows = self.db.query(
            "SELECT * FROM sections WHERE objective_id=? ORDER BY position, id", (objective_id,)
        )
        sections = []
        for r in rows:
            sec = Section(
                id=int(r["id"]),
                objective_id=objective_id,
                title=r["title"],
                position=int(r["position"]),
                collapsed=bool(r["collapsed"]),
            )
            sec.tasks = self._tasks_for(sec.id)
            sections.append(sec)
        return sections

    def _tasks_for(self, section_id: int) -> list[Task]:
        rows = self.db.query(
            "SELECT * FROM tasks WHERE section_id=? ORDER BY position, id", (section_id,)
        )
        return [
            Task(
                id=int(r["id"]),
                section_id=section_id,
                text=r["text"],
                done=bool(r["done"]),
                priority=int(r["priority"]),
                icon=r["icon"],
                position=int(r["position"]),
                completed_at=r["completed_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    def seed_if_empty(self) -> None:
        """First-launch sample data. Fully editable and deletable by the user."""
        row = self.db.query_one("SELECT COUNT(*) AS n FROM objectives")
        if row and int(row["n"]) > 0:
            return
        obj_id = self.create_objective(SEED_OBJECTIVE["title"], SEED_OBJECTIVE["subtitle"])
        for sec_title, tasks in SEED_OBJECTIVE["sections"]:
            sec_id = self.create_section(obj_id, sec_title)
            for text, done, priority, icon in tasks:
                task_id = self.create_task(sec_id, text, priority, icon)
                if done:
                    self.set_task_done(task_id, True)
