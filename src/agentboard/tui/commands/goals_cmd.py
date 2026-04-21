from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from agentboard.tui.app import DevBoardApp


# Ordered from "least done" to "most done"; used to pick the most-progressed
# task status per goal when deriving the visual marker.
_TASK_RANK = [
    "failed",
    "blocked",
    "todo",
    "planning",
    "in_progress",
    "reviewing",
    "awaiting_approval",
    "converged",
    "pushed",
]

_STATUS_MARKER: dict[str, str] = {
    "pushed": "✓",
    "converged": "●",
    "awaiting_approval": "?",
    "reviewing": "?",
    "in_progress": "▶",
    "planning": "·",
    "todo": "○",
    "blocked": "✗",
    "failed": "✗",
    "active": "·",
    "archived": "-",
}


def _derive_marker(store_root: Path, goal_id: str, declared_status: str) -> str:
    """Return a one-char marker reflecting the most-progressed task for a
    goal, or the declared goal status if there are no tasks on disk."""
    tasks_dir = store_root / ".devboard" / "goals" / goal_id / "tasks"
    statuses: list[str] = []
    if tasks_dir.exists():
        for t_dir in tasks_dir.iterdir():
            task_json = t_dir / "task.json"
            if not task_json.is_file():
                continue
            try:
                data = json.loads(task_json.read_text())
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            s = data.get("status")
            if isinstance(s, str):
                statuses.append(s)
    if statuses:
        picked = max(
            statuses,
            key=lambda s: _TASK_RANK.index(s) if s in _TASK_RANK else -1,
        )
        return _STATUS_MARKER.get(picked, "·")
    return _STATUS_MARKER.get(declared_status, "·")


def register(app: "DevBoardApp") -> None:
    app.commands.register("goals", [], lambda: _run(app))


def _run(app: "DevBoardApp") -> None:
    goals_list = app.query_one("#resources-goals", ListView)
    goals_list.clear()
    for goal in app.board.goals:
        marker = _derive_marker(app.store_root, goal.id, goal.status.value)
        goals_list.append(ListItem(Label(f"{marker} {goal.title}")))
    goals_list.focus()
