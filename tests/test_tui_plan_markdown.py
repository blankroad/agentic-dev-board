from __future__ import annotations

from pathlib import Path

import pytest


def _mk_goal(tmp_path: Path, gid: str, plan: str, gauntlet: dict[str, str] | None = None) -> None:
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

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

    from agentboard.tui.plan_markdown import PlanMarkdown
    from agentboard.tui.session_derive import SessionContext

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
async def test_raw_artifacts_section_collapsed_on_mount(tmp_path: Path) -> None:
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

        c = app.query_one("#raw-artifacts-collapsible", Collapsible)
        assert c.collapsed is True, "gauntlet section must be collapsed on mount"


@pytest.mark.asyncio
async def test_plan_markdown_prefers_summary_when_present(tmp_path: Path) -> None:
    """plan_summary.md (LLM-curated digest) must be the primary view when
    present; plan.md falls into the raw-artifacts collapsible."""
    _mk_goal(tmp_path, "g_sum", "# RAW PLAN full\n")
    goal_dir = tmp_path / ".devboard" / "goals" / "g_sum"
    (goal_dir / "plan_summary.md").write_text("# Curated Digest\n\nShort summary.\n")

    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from rich.markdown import Markdown

        body = app.query_one("#plan-body")
        content = body.content
        assert isinstance(content, Markdown)
        # The primary pane shows the summary, not the raw plan
        assert "Curated Digest" in content.markup, content.markup
        assert "RAW PLAN full" not in content.markup, (
            "raw plan leaked into primary view; should be in Raw Artifacts section"
        )


@pytest.mark.asyncio
async def test_plan_markdown_falls_back_to_plan_when_no_summary(tmp_path: Path) -> None:
    """No plan_summary.md → render plan.md as primary (current behavior)."""
    _mk_goal(tmp_path, "g_nosum", "# RAW PLAN body\n")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#plan-body")
        from rich.markdown import Markdown

        content = body.content
        assert isinstance(content, Markdown)
        assert "RAW PLAN body" in content.markup


@pytest.mark.asyncio
async def test_plan_markdown_raw_artifacts_collapsed_by_default(tmp_path: Path) -> None:
    """Raw artifacts (plan.md + gauntlet/*.md) live in a collapsible that
    is hidden on mount so the summary can breathe."""
    _mk_goal(
        tmp_path,
        "g_raw",
        "# RAW_SECRET\n",
        gauntlet={"frame": "# FRAME_SECRET"},
    )
    goal_dir = tmp_path / ".devboard" / "goals" / "g_raw"
    (goal_dir / "plan_summary.md").write_text("# SUMMARY\n")

    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import Collapsible

        col = app.query_one("#raw-artifacts-collapsible", Collapsible)
        assert col.collapsed is True, "raw artifacts must be collapsed on mount"


@pytest.mark.asyncio
async def test_plan_markdown_handles_binary_plan_md_without_crash(tmp_path: Path) -> None:
    """Red-team: a corrupted / binary plan.md must not crash the App.
    Gauntlet sections already tolerate bad files; plan.md must too."""
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_bin")
    board.goals.append(Goal(id="g_bin", title="binary", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_bin"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_bytes(b"\xff\xfe\x00broken utf8 \x80\xc0")

    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#plan-body")
        # Either the plan-body shows a sensible fallback OR the widget is
        # still present and app did not crash — either satisfies spec
        assert body is not None


@pytest.mark.asyncio
async def test_g_key_expands_raw_artifacts_section(tmp_path: Path) -> None:
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

        c = app.query_one("#raw-artifacts-collapsible", Collapsible)
        assert c.collapsed is True
        app.query_one("#pm").focus()
        await pilot.press("g")
        await pilot.pause()
        assert c.collapsed is False, "'g' key should expand gauntlet section"
