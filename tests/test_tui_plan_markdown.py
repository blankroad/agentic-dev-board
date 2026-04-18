from __future__ import annotations

from pathlib import Path

import pytest


def _mk_goal(tmp_path: Path, gid: str, plan: str, gauntlet: dict[str, str] | None = None) -> None:
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir(exist_ok=True)
    store = FileStore(tmp_path)
    try:
        board = store.load_board()
    except Exception:
        board = BoardState()
    board.goals.append(Goal(id=gid, title=gid, status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / gid
    goal_dir.mkdir(parents=True, exist_ok=True)
    (goal_dir / "plan.md").write_text(plan)
    if gauntlet:
        gdir = goal_dir / "gauntlet"
        gdir.mkdir()
        for name, body in gauntlet.items():
            (gdir / f"{name}.md").write_text(body)


async def _mount(tmp_path: Path):
    from textual.app import App, ComposeResult

    from devboard.tui.plan_markdown import PlanMarkdown
    from devboard.tui.session_derive import SessionContext

    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield PlanMarkdown(ctx, id="pm")

    return _Host()


@pytest.mark.asyncio
async def test_plan_markdown_renders_plan_md(tmp_path: Path) -> None:
    _mk_goal(tmp_path, "g1", "# MyPlan\n\nStep 1: ship\n")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from rich.markdown import Markdown

        body = app.query_one("#plan-body")
        content = body.content
        assert isinstance(content, Markdown), type(content).__name__
        assert "MyPlan" in content.markup or "Step 1" in content.markup


@pytest.mark.asyncio
async def test_gauntlet_section_collapsed_on_mount(tmp_path: Path) -> None:
    _mk_goal(
        tmp_path,
        "g2",
        "# P\n",
        gauntlet={"frame": "# FRAME_SECRET", "challenge": "# CHALLENGE_SECRET"},
    )
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import Collapsible

        c = app.query_one("#gauntlet-collapsible", Collapsible)
        assert c.collapsed is True, "gauntlet section must be collapsed on mount"


@pytest.mark.asyncio
async def test_g_key_expands_gauntlet_section(tmp_path: Path) -> None:
    _mk_goal(
        tmp_path,
        "g3",
        "# P\n",
        gauntlet={"frame": "# FRAME"},
    )
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import Collapsible

        c = app.query_one("#gauntlet-collapsible", Collapsible)
        assert c.collapsed is True
        app.query_one("#pm").focus()
        await pilot.press("g")
        await pilot.pause()
        assert c.collapsed is False, "'g' key should expand gauntlet section"
