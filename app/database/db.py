"""SQLite connection and schema management."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from ..core import paths

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS objectives (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    subtitle    TEXT    NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id INTEGER NOT NULL REFERENCES objectives(id) ON DELETE CASCADE,
    title        TEXT    NOT NULL,
    position     INTEGER NOT NULL DEFAULT 0,
    collapsed    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sections_objective ON sections(objective_id, position);

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id   INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    text         TEXT    NOT NULL,
    done         INTEGER NOT NULL DEFAULT 0,
    priority     INTEGER NOT NULL DEFAULT 0,
    icon         TEXT    NOT NULL DEFAULT '',
    position     INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    timer_enabled INTEGER NOT NULL DEFAULT 0,
    timer_target  INTEGER NOT NULL DEFAULT 0,
    timer_elapsed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_section ON tasks(section_id, position);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Columns introduced after schema v1, patched into existing databases.
_ADDED_COLUMNS = (
    ("tasks", "timer_enabled", "timer_enabled INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "timer_target", "timer_target INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "timer_elapsed", "timer_elapsed INTEGER NOT NULL DEFAULT 0"),
)


class Database:
    """Thin wrapper around a single sqlite connection.

    The app is single-threaded for data access; the lock only guards against
    the audio/hotkey helpers ever touching the connection from a timer thread.
    """

    def __init__(self, path: Path | None = None) -> None:
        # Resolved through the module, not a name imported at import time: the
        # test harnesses redirect the app at a throwaway database by patching
        # paths.database_path, and a bound name would ignore that and open the
        # user's real data instead.
        self.path = Path(path) if path else paths.database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._closed = False
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self._add_missing_columns()
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
            self.conn.commit()

    def _add_missing_columns(self) -> None:
        """Bring a v1 database up to date in place.

        SQLite has no ``ADD COLUMN IF NOT EXISTS``, and the CREATE TABLE above
        is skipped entirely for an existing table -- so columns added after v1
        have to be patched in one by one against the live schema.
        """
        for table, column, ddl in _ADDED_COLUMNS:
            existing = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    # -- helpers ---------------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def close(self) -> None:
        """Commit and close. Idempotent -- a second call is a no-op.

        Shutdown can reach this from more than one path, and raising here
        aborts whatever teardown still had to run.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self.conn.commit()
            except sqlite3.ProgrammingError:
                pass          # already closed underneath us; nothing to flush
            finally:
                self.conn.close()

    @property
    def is_closed(self) -> bool:
        return self._closed
