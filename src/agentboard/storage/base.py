from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from agentboard.models import BoardState, Goal, Task, LockedPlan


class Repository(ABC):
    @abstractmethod
    def load_board(self) -> BoardState: ...

    @abstractmethod
    def save_board(self, state: BoardState) -> None: ...

    @abstractmethod
    def load_goal(self, goal_id: str) -> Goal | None: ...

    @abstractmethod
    def save_goal(self, goal: Goal) -> None: ...

    @abstractmethod
    def load_task(self, goal_id: str, task_id: str) -> Task | None: ...

    @abstractmethod
    def save_task(self, task: Task) -> None: ...

    @abstractmethod
    def load_locked_plan(self, goal_id: str) -> LockedPlan | None: ...

    @abstractmethod
    def save_locked_plan(self, plan: LockedPlan) -> None: ...

    @abstractmethod
    def save_iter_diff(self, task_id: str, iter_n: int, diff: str) -> None: ...

    @abstractmethod
    def append_decision(self, task_id: str, entry: dict) -> None: ...

    @abstractmethod
    def save_gauntlet_step(self, goal_id: str, step_name: str, content: str) -> None: ...
