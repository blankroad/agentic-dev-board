from __future__ import annotations

import json
from pathlib import Path

import pytest


def _mk_decisions(tmp_path: Path) -> tuple[str, str]:
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".agentboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState()
    board.goals.append(Goal(id="g_1", title="g", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".agentboard" / "goals" / "g_1"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# p\n")
    task_dir = goal_dir / "tasks" / "t_1"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_1", "status": "in_progress"}))
    (task_dir / "decisions.jsonl").write_text(
        json.dumps({"iter": 1, "phase": "tdd_red", "ts": "2026-04-18 01:01:01+00:00"}) + "\n"
        + json.dumps({"iter": 2, "phase": "tdd_green", "ts": "2026-04-18 02:02:02+00:00"}) + "\n"
        + json.dumps({"iter": 3, "phase": "redteam", "verdict_source": "BROKEN",
                      "ts": "2026-04-18 03:03:03+00:00"}) + "\n"
    )
    return "g_1", "t_1"


@pytest.mark.asyncio
async def test_timeline_collapsed_by_default_with_summary_title(tmp_path: Path) -> None:
    """Spec: timeline shows a single-line summary by default; full rows
    are hidden behind a Collapsible until 't' expands them."""
    from textual.app import App, ComposeResult
    from textual.widgets import Collapsible

    from agentboard.tui.activity_timeline import ActivityTimeline
    from agentboard.tui.session_derive import SessionContext

    _mk_decisions(tmp_path)
    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield ActivityTimeline(ctx, task_id="t_1", id="tl")

    app = _Host()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        col = app.query_one("#activity-collapsible", Collapsible)
        assert col.collapsed is True, "timeline must be collapsed on mount"
        # Title must contain summary
        title = str(col.title)
        assert "Activity" in title and "iter" in title, (
            f"summary title missing expected segments; got {title!r}"
        )


@pytest.mark.asyncio
async def test_timeline_renders_rows_newest_first(tmp_path: Path) -> None:
    from textual.app import App, ComposeResult

    from agentboard.tui.activity_row import ActivityRow
    from agentboard.tui.activity_timeline import ActivityTimeline
    from agentboard.tui.session_derive import SessionContext

    _mk_decisions(tmp_path)
    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield ActivityTimeline(ctx, task_id="t_1", id="tl")

    app = _Host()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        rows = list(app.query(ActivityRow).results())
        assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"
        iters = [r.entry.get("iter") for r in rows]
        assert iters == [3, 2, 1], f"expected newest-first; got {iters}"
