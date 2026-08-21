"""Parsing and formatting for task timer durations.

Targets are typed by hand ("21h", "1h 30m", "90m", "2:30"), so the parser is
deliberately forgiving; everything is stored as a plain number of seconds.
"""
from __future__ import annotations

import re

_UNITS = {
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
}
_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([a-z]*)")

MAX_TARGET = 999 * 3600      # a sane ceiling; keeps the chip from overflowing


def parse_duration(text: str) -> int:
    """Return seconds for a hand-typed duration, or 0 when nothing parses.

    Accepted forms::

        21h        1h30m      1h 30m 15s      90m       45s
        2:30       (h:mm)     1:05:30         (h:mm:ss)
        45         (bare number -- minutes)

    A bare number means *minutes*: "45" is the common way to write a
    three-quarter-hour session, and hours would be a surprising default.
    """
    raw = (text or "").strip().lower()
    if not raw or "-" in raw:
        # A negative target is meaningless, and silently reading "-5m" as five
        # minutes would hide the typo rather than flag it.
        return 0

    if ":" in raw:
        parts = raw.split(":")
        if len(parts) > 3 or not all(p.strip().isdigit() for p in parts if p.strip() != ""):
            return 0
        nums = [int(p) if p.strip() else 0 for p in parts]
        if len(nums) == 2:                       # h:mm
            hours, minutes, seconds = nums[0], nums[1], 0
        else:                                    # h:mm:ss
            hours, minutes, seconds = nums
        return _clamp(hours * 3600 + minutes * 60 + seconds)

    total = 0.0
    matched = False
    for value, unit in _UNIT_RE.findall(raw):
        matched = True
        if unit == "":
            total += float(value) * 60          # bare number -> minutes
        elif unit in _UNITS:
            total += float(value) * _UNITS[unit]
        else:
            return 0
    return _clamp(int(round(total))) if matched else 0


def _clamp(seconds: int) -> int:
    return max(0, min(MAX_TARGET, int(seconds)))


def format_clock(seconds: int, blink_off: bool = False) -> str:
    """``MM:SS`` under an hour, ``H:MM:SS`` above -- the chip's read-out.

    ``blink_off`` blanks the separators for the off half of the one-second
    blink a running clock does.
    """
    seconds = max(0, int(seconds))
    sep = " " if blink_off else ":"
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}{sep}{minutes:02d}{sep}{secs:02d}"
    return f"{minutes:02d}{sep}{secs:02d}"


def format_compact(seconds: int) -> str:
    """Short human form used for targets: ``21h``, ``1h 30m``, ``45m``."""
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "-"
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours and minutes:
        return f"{hours}h {minutes:02d}m"
    if hours:
        return f"{hours}h"
    if minutes and secs:
        return f"{minutes}m {secs:02d}s"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"
