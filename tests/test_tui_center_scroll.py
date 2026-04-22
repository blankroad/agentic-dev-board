from __future__ import annotations

import json
from pathlib import Path

import pytest


def _bootstrap_minimal(tmp_path: Path) -> None:
    """Minimal SessionContext-compatible fixture — one active goal with a
    short plan. Enough for PhaseFlowView to compose without errors."""
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_s")
    board.goals.append(Goal(id="g_s", title="scroll-fixture", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_s"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# plan\n")


@pytest.mark.asyncio
async def test_overview_tab_wraps_static_in_vertical_scroll(tmp_path: Path) -> None:
    """s_001 — #overview TabPane must contain a VerticalScroll node as a
    descendant so that overflowing overview body can be scrolled via
    keyboard/wheel. Before fix: TabPane holds Static directly → no scroll."""
    from textual.containers import VerticalScroll
    from textual.widgets import TabPane

    from agentboard.tui.app import AgentBoardApp

    _bootstrap_minimal(tmp_path)
    app = AgentBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        overview_pane = app.query_one("#overview", TabPane)
        scrolls = list(overview_pane.query(VerticalScroll))
        assert scrolls, (
            "#overview TabPane must contain a VerticalScroll descendant "
            "so that ↓/PgDn/wheel can scroll its body"
        )


def _bootstrap_with_long_plan(tmp_path: Path, lines: int = 200) -> None:
    """Fixture with a plan.md far longer than any viewport so the
    Plan tab's VerticalScroll is guaranteed to overflow."""
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_s")
    board.goals.append(Goal(id="g_s", title="scroll-long", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_s"
    goal_dir.mkdir(parents=True)
    body = "\n".join(f"## section {i}\n\nparagraph body line {i}." for i in range(lines))
    (goal_dir / "plan.md").write_text(body)


@pytest.mark.asyncio
async def test_down_key_scrolls_plan_viewport(tmp_path: Path) -> None:
    """s_003 — with long plan content, pressing ↓ must increase the Plan
    tab's VerticalScroll.scroll_y. This validates the critical-path
    Riskiest Assumption: wrapping TabPane body in VerticalScroll actually
    routes keyboard scroll events to the scroll container."""
    from textual.containers import VerticalScroll
    from textual.widgets import TabPane

    from agentboard.tui.app import AgentBoardApp

    _bootstrap_with_long_plan(tmp_path, lines=300)
    app = AgentBoardApp(store_root=tmp_path)
    # Intentionally small viewport so even a modest plan overflows.
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        # Switch to Plan tab (number-key binding)
        await pilot.press("2")
        await pilot.pause()
        plan_pane = app.query_one("#plan", TabPane)
        vs = plan_pane.query_one(VerticalScroll)
        assert vs.scroll_y == 0, f"precondition: scroll_y starts at 0, got {vs.scroll_y}"
        # Give scroll container focus explicitly — key-binding routing
        # from App-level priority bindings (1/2/3/4/5) could otherwise
        # leave focus on an unrelated widget.
        vs.focus()
        await pilot.pause()
        for _ in range(15):
            await pilot.press("down")
        await pilot.pause()
        assert vs.scroll_y > 0, (
            f"after pressing ↓ 15 times on Plan tab's VerticalScroll, "
            f"scroll_y must advance beyond 0; got {vs.scroll_y}"
        )


@pytest.mark.asyncio
async def test_down_key_scrolls_on_real_user_flow_without_explicit_focus(
    tmp_path: Path,
) -> None:
    """s_009 — redteam CRITICAL: on the real user flow (no explicit
    vs.focus()), pressing a tab number key and then ↓ must scroll the
    center tab's viewport. Before fix: on_mount focuses ListView
    #resources-goals which consumes ↓/PgDn for its own cursor, so the
    VerticalScroll never receives the keys. After fix: either the tab
    switch focuses the new tab's VerticalScroll, or boot focus starts on
    the center scroll container."""
    from textual.containers import VerticalScroll
    from textual.widgets import TabPane

    from agentboard.tui.app import AgentBoardApp

    _bootstrap_with_long_plan(tmp_path, lines=300)
    app = AgentBoardApp(store_root=tmp_path)
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        # Real user flow: switch to Plan via number key then just press ↓.
        # No explicit .focus() call.
        await pilot.press("2")
        await pilot.pause()
        for _ in range(15):
            await pilot.press("down")
        await pilot.pause()
        plan_pane = app.query_one("#plan", TabPane)
        vs = plan_pane.query_one(VerticalScroll)
        assert vs.scroll_y > 0, (
            f"plan tab must scroll when user presses ↓ after tab switch "
            f"(no explicit focus call); got scroll_y={vs.scroll_y}"
        )


# historical scope-guard removed (rename-the-world goal)


def test_center_col_width_is_1fr() -> None:
    """s_007 — AgentBoardApp.CSS must set #center-col width to 1fr (so the
    PhaseFlowView absorbs the horizontal space freed by removing
    #right-col). A lingering `width: 65%` literal would leave a dead
    20% void on the right of the screen."""
    from agentboard.tui.app import AgentBoardApp

    css = AgentBoardApp.CSS
    assert "#center-col { width: 1fr; }" in css, (
        f"#center-col must use width: 1fr; full CSS:\n{css}"
    )
    assert "65%" not in css, f"stale `65%` literal in CSS:\n{css}"


def test_no_dangling_references_in_src() -> None:
    """s_006 — the src/ tree must no longer contain any of the strings
    that named the deleted right-panel widgets. Catches partial cleanups
    like a stale import, a dead docstring, or a lingering CSS rule."""
    import re

    repo = Path(__file__).resolve().parent.parent
    src = repo / "src"
    patterns = ("MetaPane", "FilesChangedPane", "meta-pane", "files-changed-pane", "#right-col")
    regex = re.compile("|".join(re.escape(p) for p in patterns))
    offenders: list[str] = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if regex.search(text):
            offenders.append(str(py.relative_to(repo)))
    assert not offenders, (
        f"these src/ files still reference deleted widgets: {offenders}"
    )


def test_deprecated_widget_files_removed() -> None:
    """s_005 — meta_pane.py / files_changed_pane.py and their dedicated
    test files must all be removed. Leaving them behind creates dead
    imports and misleads future readers about active widgets."""
    repo = Path(__file__).resolve().parent.parent
    must_be_gone = [
        repo / "src" / "agentboard" / "tui" / "meta_pane.py",
        repo / "src" / "agentboard" / "tui" / "files_changed_pane.py",
        repo / "tests" / "test_tui_meta_pane.py",
        repo / "tests" / "test_tui_files_changed_pane.py",
    ]
    lingering = [str(p.relative_to(repo)) for p in must_be_gone if p.exists()]
    assert not lingering, f"these deprecated files must be deleted: {lingering}"


@pytest.mark.asyncio
async def test_app_has_no_right_col_container(tmp_path: Path) -> None:
    """s_004 — AgentBoardApp.compose() must not yield the legacy #right-col
    container. MetaPane + FilesChangedPane are being removed; the
    container that held them must go with them to free up horizontal
    space for the center PhaseFlowView."""
    from textual.css.query import NoMatches

    from agentboard.tui.app import AgentBoardApp

    _bootstrap_minimal(tmp_path)
    app = AgentBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        with pytest.raises(NoMatches):
            app.query_one("#right-col")


@pytest.mark.asyncio
async def test_all_five_tabs_wrap_body_in_vertical_scroll(tmp_path: Path) -> None:
    """s_002 — plan/dev/result/review TabPanes must ALSO wrap their body
    in a VerticalScroll. overview alone is insufficient; every tab can
    overflow depending on content volume (long plan, many iterations)."""
    from textual.containers import VerticalScroll
    from textual.widgets import TabPane

    from agentboard.tui.app import AgentBoardApp

    _bootstrap_minimal(tmp_path)
    app = AgentBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        missing: list[str] = []
        for tab_id in ("overview", "plan", "dev", "result", "review"):
            pane = app.query_one(f"#{tab_id}", TabPane)
            if not list(pane.query(VerticalScroll)):
                missing.append(tab_id)
        assert not missing, (
            f"Every PhaseFlowView TabPane must wrap its body in VerticalScroll; "
            f"missing in tabs: {missing}"
        )
