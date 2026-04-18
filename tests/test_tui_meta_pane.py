from __future__ import annotations

import json
from pathlib import Path

import pytest


def _mk(tmp_path: Path, atomic_steps: int = 25, completed: int = 10) -> tuple[str, str]:
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_m")
    board.goals.append(Goal(id="g_m", title="g", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_m"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# p\n")
    plan_json = {
        "atomic_steps": [
            {"id": f"s_{i:03d}", "completed": i < completed} for i in range(atomic_steps)
        ]
    }
    (goal_dir / "plan.json").write_text(json.dumps(plan_json))
    task_dir = goal_dir / "tasks" / "t_m"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_m", "status": "in_progress"}))
    (task_dir / "decisions.jsonl").write_text(
        json.dumps({"iter": 5, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED"}) + "\n"
    )
    return "g_m", "t_m"


@pytest.mark.asyncio
async def test_meta_pane_iter_and_verdict(tmp_path: Path) -> None:
    from textual.app import App, ComposeResult

    from devboard.tui.meta_pane import MetaPane
    from devboard.tui.session_derive import SessionContext

    _mk(tmp_path)
    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield MetaPane(ctx, task_id="t_m", selected_iter=5, id="mp")

    app = _Host()
    async with app.run_test(size=(40, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#meta-body")
        text = str(body.render())
        assert "iter" in text.lower() and "5" in text, text
        assert "GREEN_CONFIRMED" in text or "verdict" in text.lower(), text


@pytest.mark.asyncio
async def test_meta_pane_steps_progress(tmp_path: Path) -> None:
    from textual.app import App, ComposeResult

    from devboard.tui.meta_pane import MetaPane
    from devboard.tui.session_derive import SessionContext

    _mk(tmp_path, atomic_steps=25, completed=10)
    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield MetaPane(ctx, task_id="t_m", selected_iter=5, id="mp")

    app = _Host()
    async with app.run_test(size=(40, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#meta-body")
        text = str(body.render())
        assert "10/25" in text, f"expected 'steps: 10/25' line; got {text!r}"
