"""Windows global hotkey support.

Uses ``RegisterHotKey`` plus a Qt native event filter to catch ``WM_HOTKEY``.
This needs no third-party dependency and no polling -- the message only
arrives when the user actually presses the combination.

On non-Windows platforms every call degrades to a no-op so the rest of the
app (and the test suite) still runs.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

IS_WINDOWS = sys.platform == "win32"

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
    "super": MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "insert": 0x2D,
    "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "pgup": 0x21, "pageup": 0x21, "pgdn": 0x22, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
for _i in range(1, 25):
    _NAMED_KEYS[f"f{_i}"] = 0x6F + _i


class HotkeyError(RuntimeError):
    pass


def parse_sequence(sequence: str) -> tuple[int, int]:
    """Turn e.g. ``"Ctrl+Shift+Q"`` into ``(modifiers, virtual_key)``."""
    parts = [p.strip().lower() for p in str(sequence).split("+") if p.strip()]
    if not parts:
        raise HotkeyError("empty hotkey")

    mods = 0
    key: int | None = None
    for part in parts:
        if part in _MODIFIERS:
            mods |= _MODIFIERS[part]
        elif part in _NAMED_KEYS:
            key = _NAMED_KEYS[part]
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())
        else:
            raise HotkeyError(f"unrecognised key: {part!r}")

    if key is None:
        raise HotkeyError("hotkey needs a non-modifier key")
    if mods == 0:
        raise HotkeyError("hotkey needs at least one modifier")
    return mods | MOD_NOREPEAT, key


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: "HotkeyManager") -> None:
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt signature)
        if not IS_WINDOWS or event_type not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
        except (ValueError, TypeError):
            return False, 0
        if msg.message == WM_HOTKEY and msg.wParam == self._manager.hotkey_id:
            self._manager.activated.emit()
            return True, 0
        return False, 0


class HotkeyManager(QObject):
    """Registers exactly one global hotkey and emits :attr:`activated`."""

    activated = Signal()

    hotkey_id = 0xB011

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registered = False
        self._sequence = ""
        self._filter: _HotkeyFilter | None = None

    @property
    def sequence(self) -> str:
        return self._sequence

    @property
    def is_registered(self) -> bool:
        return self._registered

    def install(self, app) -> None:
        if not IS_WINDOWS or self._filter is not None:
            return
        self._filter = _HotkeyFilter(self)
        app.installNativeEventFilter(self._filter)

    def register(self, sequence: str) -> None:
        """(Re)register the hotkey. Raises :class:`HotkeyError` on failure."""
        mods, key = parse_sequence(sequence)
        self.unregister()
        if not IS_WINDOWS:
            self._sequence = sequence
            return
        ok = ctypes.windll.user32.RegisterHotKey(None, self.hotkey_id, mods, key)
        if not ok:
            raise HotkeyError(
                f"'{sequence}' is already claimed by another application"
            )
        self._registered = True
        self._sequence = sequence

    def unregister(self) -> None:
        if self._registered and IS_WINDOWS:
            ctypes.windll.user32.UnregisterHotKey(None, self.hotkey_id)
        self._registered = False
