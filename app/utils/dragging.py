"""Let inert areas of the panel drag the frameless window."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


def try_start_drag(widget: QWidget, event) -> bool:
    """Begin a native window move if the press was a plain left click.

    Refuses when the press landed on a child widget. Interactive children
    accept their own presses, but if one ever forgets, starting a native move
    loop here would swallow the release and silently break that widget's
    click -- a failure that does not reproduce on the offscreen test platform,
    where startSystemMove() is a no-op.
    """
    if event.button() != Qt.MouseButton.LeftButton:
        return False

    position = event.position().toPoint()
    child = widget.childAt(position)
    if child is not None and child is not widget:
        return False

    window = widget.window()
    handle = window.windowHandle() if window else None
    if handle is None:
        return False
    return bool(handle.startSystemMove())
