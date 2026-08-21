"""Runs the per-task clocks.

One shared one-second QTimer drives every running task, so the panel never
accumulates a timer per row. Elapsed seconds are measured against a monotonic
clock -- not by counting ticks -- so a stalled event loop or a sleeping machine
cannot quietly lose time.

Running state is deliberately *not* persisted: a timer left running when the
app closes comes back paused, at its last banked total. Restoring it as running
would silently bill every offline hour to the task.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..database.repo import Repo

FLUSH_EVERY = 15          # seconds between writes of a running total


class TimerService(QObject):
    tick = Signal(int, int)            # task id, elapsed seconds
    state_changed = Signal(int, bool)  # task id, running
    target_reached = Signal(int)       # task id, the moment it hits its goal

    def __init__(self, repo: Repo, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        # task id -> (monotonic start, seconds already banked at that start)
        self._running: dict[int, tuple[float, int]] = {}
        self._targets: dict[int, int] = {}
        self._announced: set[int] = set()
        self._since_flush = 0

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------
    def is_running(self, task_id: int) -> bool:
        return task_id in self._running

    def running_ids(self) -> list[int]:
        return list(self._running)

    def elapsed(self, task_id: int, stored: int) -> int:
        """Live total for a task: banked seconds plus the current run."""
        entry = self._running.get(task_id)
        if entry is None:
            return max(0, int(stored))
        start, base = entry
        return base + int(time.monotonic() - start)

    # ------------------------------------------------------------------
    def start(self, task_id: int, stored: int, target: int = 0) -> None:
        """Start one task's clock. Any other running task is paused first.

        Only one timer runs at a time on purpose: two clocks ticking at once
        would double-count a single stretch of work, and the panel is built
        around a single current task.
        """
        if task_id in self._running:
            return
        for other in list(self._running):
            self.pause(other)
        self._running[task_id] = (time.monotonic(), max(0, int(stored)))
        self._targets[task_id] = max(0, int(target))
        if not target or stored < target:
            self._announced.discard(task_id)
        else:
            self._announced.add(task_id)      # already past its goal; stay quiet
        if not self._timer.isActive():
            self._since_flush = 0
            self._timer.start()
        self.state_changed.emit(task_id, True)

    def pause(self, task_id: int) -> int:
        """Stop one clock and bank its total. Returns the elapsed seconds."""
        entry = self._running.pop(task_id, None)
        self._targets.pop(task_id, None)
        if entry is None:
            return self.repo.task_elapsed(task_id)
        start, base = entry
        elapsed = base + int(time.monotonic() - start)
        self.repo.set_task_elapsed(task_id, elapsed)
        if not self._running:
            self._timer.stop()
        self.state_changed.emit(task_id, False)
        self.tick.emit(task_id, elapsed)
        return elapsed

    def toggle(self, task_id: int, stored: int, target: int = 0) -> bool:
        """Flip one task between running and paused. Returns the new state."""
        if task_id in self._running:
            self.pause(task_id)
            return False
        self.start(task_id, stored, target)
        return True

    def reset(self, task_id: int) -> None:
        self._running.pop(task_id, None)
        self._targets.pop(task_id, None)
        self._announced.discard(task_id)
        self.repo.reset_task_timer(task_id)
        if not self._running:
            self._timer.stop()
        self.state_changed.emit(task_id, False)
        self.tick.emit(task_id, 0)

    def pause_all(self) -> None:
        for task_id in list(self._running):
            self.pause(task_id)

    def forget(self, task_id: int) -> None:
        """Drop a deleted task without writing its total back to a gone row."""
        self._running.pop(task_id, None)
        self._targets.pop(task_id, None)
        self._announced.discard(task_id)
        if not self._running:
            self._timer.stop()

    def shutdown(self) -> None:
        """Bank every running total before the database closes."""
        self._timer.stop()
        for task_id in list(self._running):
            self.pause(task_id)

    # ------------------------------------------------------------------
    def _on_tick(self) -> None:
        self._since_flush += 1
        flush = self._since_flush >= FLUSH_EVERY
        if flush:
            self._since_flush = 0
        for task_id in list(self._running):
            start, base = self._running[task_id]
            elapsed = base + int(time.monotonic() - start)
            if flush:
                self.repo.set_task_elapsed(task_id, elapsed)
            self.tick.emit(task_id, elapsed)
            self._check_target(task_id, elapsed)

    def _check_target(self, task_id: int, elapsed: int) -> None:
        if task_id in self._announced:
            return
        target = self._targets.get(task_id, 0)
        if target and elapsed >= target:
            self._announced.add(task_id)
            self.repo.set_task_elapsed(task_id, elapsed)
            self.target_reached.emit(task_id)
