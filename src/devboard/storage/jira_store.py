"""Jira sync adapter — stub for Phase E."""
from __future__ import annotations

from pathlib import Path

from devboard.models import BoardState, Goal, LockedPlan, Task
from devboard.storage.base import Repository
from devboard.storage.file_store import FileStore


class JiraStore(Repository):
    """Local FileStore + Jira bidirectional sync (Phase E stub)."""

    def __init__(self, root: Path, jira_base_url: str, jira_token: str) -> None:
        self._local = FileStore(root)
        self._jira_base_url = jira_base_url
        self._jira_token = jira_token

    def load_board(self) -> BoardState:
        return self._local.load_board()

    def save_board(self, state: BoardState) -> None:
        self._local.save_board(state)

    def load_goal(self, goal_id: str) -> Goal | None:
        return self._local.load_goal(goal_id)

    def save_goal(self, goal: Goal) -> None:
        self._local.save_goal(goal)
        # TODO Phase E: push status update to Jira

    def load_task(self, goal_id: str, task_id: str) -> Task | None:
        return self._local.load_task(goal_id, task_id)

    def save_task(self, task: Task) -> None:
        self._local.save_task(task)
        # TODO Phase E: update Jira subtask

    def load_locked_plan(self, goal_id: str) -> LockedPlan | None:
        return self._local.load_locked_plan(goal_id)

    def save_locked_plan(self, plan: LockedPlan) -> None:
        self._local.save_locked_plan(plan)

    def save_iter_diff(self, task_id: str, iter_n: int, diff: str) -> None:
        self._local.save_iter_diff(task_id, iter_n, diff)

    def append_decision(self, task_id: str, entry: dict) -> None:
        self._local.append_decision(task_id, entry)

    def save_gauntlet_step(self, goal_id: str, step_name: str, content: str) -> None:
        self._local.save_gauntlet_step(goal_id, step_name, content)
