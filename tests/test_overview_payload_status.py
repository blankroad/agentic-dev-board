"""s_001 — payload.current_state.status must reflect task.json.status
(not hardcoded 'in_progress'). Fixes R1 Overview tab stale status bug."""

from __future__ import annotations

import json
from pathlib import Path


def _bootstrap_pushed_task(tmp_path: Path) -> tuple[str, str]:
    """Create a goal + task whose task.json says status='pushed'. Returns
    (goal_id, task_id)."""
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_pushed")
    board.goals.append(Goal(id="g_pushed", title="done-goal", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_pushed"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# plan\n")
    task_dir = goal_dir / "tasks" / "t_pushed"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(
        json.dumps({"id": "t_pushed", "status": "pushed"})
    )
    (task_dir / "decisions.jsonl").write_text(
        json.dumps({"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED"}) + "\n"
    )
    return "g_pushed", "t_pushed"


def test_current_state_status_reflects_task_json(tmp_path: Path) -> None:
    """payload.current_state.status must be 'pushed' when task.json says so.
    Before fix: hardcoded 'in_progress' regardless of task state."""
    from agentboard.analytics.overview_payload import build_overview_payload

    goal_id, task_id = _bootstrap_pushed_task(tmp_path)
    payload = build_overview_payload(tmp_path, goal_id, task_id=task_id)
    assert payload["current_state"]["status"] == "pushed", (
        f"expected status='pushed' from task.json, got "
        f"{payload['current_state'].get('status')!r}"
    )
