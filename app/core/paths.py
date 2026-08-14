"""Filesystem locations for assets and user data.

Resolves correctly both when running from source and when frozen by
PyInstaller (where assets live in the temporary ``_MEIPASS`` extraction dir
but user data must go somewhere writable and permanent).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "QuestPanel"


def _frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_root() -> Path:
    """Directory containing the read-only ``assets`` tree."""
    if _frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def assets_dir() -> Path:
    return resource_root() / "assets"


def asset(*parts: str) -> Path:
    return assets_dir().joinpath(*parts)


def data_dir() -> Path:
    """Writable directory for the database and logs."""
    if _frozen():
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = resource_root() / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def database_path() -> Path:
    return data_dir() / "questpanel.db"


def user_audio_dir() -> Path:
    """Writable audio folder that survives reinstalls and app updates.

    The bundled ``assets/audio`` lives inside the PyInstaller payload, which is
    an awkward place to ask someone to drop an mp3 -- and it is wiped on every
    rebuild. This folder is the one the UI points people at.
    """
    base = data_dir() / "audio"
    (base / "music").mkdir(parents=True, exist_ok=True)
    return base


def audio_search_dirs() -> list[Path]:
    """Where to look for audio, highest priority first."""
    dirs = [user_audio_dir()]
    bundled = assets_dir() / "audio"
    if bundled.is_dir():
        dirs.append(bundled)
    return dirs
