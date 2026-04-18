from __future__ import annotations

import json
from pathlib import Path

import pytest


def _mk_goal(tmp_path: Path, gid: str, title: str, task_status: str | None = None) -> None:
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir(exist_ok=True)
    store = FileStore(tmp_path)
    try:
        board = store.load_board()
    except Exception:
        board = BoardState()
    board.goals.append(Goal(id=gid, title=title, status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / gid
    goal_dir.mkdir(parents=True, exist_ok=True)
    (goal_dir / "plan.md").write_text("# p\n")
    if task_status:
        task_dir = goal_dir / "tasks" / f"t_{gid}"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps({"id": f"t_{gid}", "status": task_status})
        )


async def _mount(tmp_path: Path):
    from textual.app import App, ComposeResult

    from devboard.tui.goal_side_list import GoalSideList
    from devboard.tui.session_derive import SessionContext

    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield GoalSideList(ctx, id="gsl")

    return _Host()


@pytest.mark.asyncio
async def test_goal_side_list_renders_all_goals_with_markers(tmp_path: Path) -> None:
    _mk_goal(tmp_path, "g_shipped", "shipped-goal", task_status="pushed")
    _mk_goal(tmp_path, "g_wip", "wip-goal", task_status="in_progress")
    app = await _mount(tmp_path)
    async with app.run_test(size=(40, 20)) as pilot:
        await pilot.pause()
        lv = app.query_one("#resources-goals")
        texts = []
        for item in lv.children:
            try:
                texts.append(str(item.query_one("Label").render()))
            except Exception:
                pass
        joined = " | ".join(texts)
        assert "shipped-goal" in joined, joined
        assert "wip-goal" in joined, joined
        # Markers differ between pushed and wip
        shipped_line = next(t for t in texts if "shipped-goal" in t)
        wip_line = next(t for t in texts if "wip-goal" in t)
        assert shipped_line.split("shipped-goal")[0] != wip_line.split("wip-goal")[0]


@pytest.mark.asyncio
async def test_goal_side_list_shows_inline_legend(tmp_path: Path) -> None:
    _mk_goal(tmp_path, "g1", "one", task_status="pushed")
    app = await _mount(tmp_path)
    async with app.run_test(size=(40, 20)) as pilot:
        await pilot.pause()
        legend = app.query_one("#goal-side-legend")
        text = str(legend.render())
        assert "✓" in text and "▶" in text and "✗" in text, (
            f"inline legend missing markers: {text!r}"
        )
