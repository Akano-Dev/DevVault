"""Typed key/value settings persisted in the SQLite ``settings`` table."""
from __future__ import annotations

from typing import Any

from ..database.db import Database

DEFAULTS: dict[str, Any] = {
    # General
    "start_with_windows": False,
    "always_on_top": True,
    "remember_position": True,
    "remember_size": True,
    "hotkey": "Ctrl+Shift+Q",
    "hide_to_tray": True,
    # Desktop toasts for finished timers and completed objectives.
    "notifications_enabled": True,
    # Appearance
    "ui_scale": 1.0,
    "opacity": 0.96,
    "show_icons": True,
    "show_progress": True,
    "compact_mode": False,
    "blossom_enabled": True,
    "animations_enabled": True,
    "click_through_when_unfocused": False,
    # Audio -- on by default so dropping a track into the music folder just
    # works; with an empty folder the whole audio system is a no-op anyway.
    "music_enabled": True,
    "music_volume": 0.35,
    "sfx_enabled": True,
    "sfx_volume": 0.60,
    "master_volume": 0.80,
    # Window state
    "win_x": -1,
    "win_y": -1,
    "win_w": 340,
    "win_h": 220,
    "visible_on_start": True,
    "active_objective_id": 0,
}


def _encode(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _decode(raw: str, default: Any) -> Any:
    try:
        if isinstance(default, bool):
            return raw not in ("0", "", "false", "False")
        if isinstance(default, int):
            return int(float(raw))
        if isinstance(default, float):
            return float(raw)
        return raw
    except (TypeError, ValueError):
        return default


class SettingsStore:
    """In-memory cache backed by the database; writes through immediately."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._cache: dict[str, Any] = dict(DEFAULTS)
        for row in db.query("SELECT key, value FROM settings"):
            key = row["key"]
            if key in DEFAULTS:
                self._cache[key] = _decode(row["value"], DEFAULTS[key])

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._cache:
            return self._cache[key]
        return DEFAULTS.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self._cache.get(key) == value and key in self._cache:
            return
        self._cache[key] = value
        self.db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, _encode(value)),
        )

    def update(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    # Convenience typed accessors -----------------------------------------
    def bool(self, key: str) -> bool:
        return bool(self.get(key))

    def int(self, key: str) -> int:
        return int(self.get(key))

    def float(self, key: str) -> float:
        return float(self.get(key))

    def str(self, key: str) -> str:
        return str(self.get(key))
