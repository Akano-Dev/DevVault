"""Plain data objects mirroring the database rows."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Task:
    id: int
    section_id: int
    text: str
    done: bool = False
    priority: int = 0
    icon: str = ""
    position: int = 0
    completed_at: str | None = None
    timer_enabled: bool = False
    timer_target: int = 0        # seconds; 0 means "count up, no goal"
    timer_elapsed: int = 0       # seconds banked from previous runs

    @property
    def timer_remaining(self) -> int:
        """Seconds left against the target. 0 once the target is met."""
        if not self.timer_target:
            return 0
        return max(0, self.timer_target - self.timer_elapsed)

    @property
    def timer_progress(self) -> float:
        """0.0 - 1.0 toward the target; a goal-less timer never fills."""
        if not self.timer_target:
            return 0.0
        return min(1.0, self.timer_elapsed / self.timer_target)

    @property
    def timer_reached(self) -> bool:
        return bool(self.timer_target) and self.timer_elapsed >= self.timer_target


@dataclass(slots=True)
class Section:
    id: int
    objective_id: int
    title: str
    position: int = 0
    collapsed: bool = False
    tasks: list[Task] = field(default_factory=list)

    @property
    def done_count(self) -> int:
        return sum(1 for t in self.tasks if t.done)

    @property
    def total_count(self) -> int:
        return len(self.tasks)


@dataclass(slots=True)
class Objective:
    id: int
    title: str
    subtitle: str = ""
    position: int = 0
    is_active: bool = False
    sections: list[Section] = field(default_factory=list)

    @property
    def tasks(self) -> list[Task]:
        return [t for s in self.sections for t in s.tasks]

    @property
    def done_count(self) -> int:
        return sum(1 for t in self.tasks if t.done)

    @property
    def total_count(self) -> int:
        return len(self.tasks)

    @property
    def progress(self) -> float:
        """0.0 - 1.0. An objective with no tasks counts as 0%, not 100%."""
        total = self.total_count
        return (self.done_count / total) if total else 0.0

    @property
    def is_complete(self) -> bool:
        return self.total_count > 0 and self.done_count == self.total_count
