"""v2.1-compatible smoke tests retained from the v2.0 suite.

Tests that asserted v2.0-specific widgets (ContextViewer tabs,
LiveStreamView as a 45% pane, #resources-runs list) were removed in
the v2.1 migration per the LockedPlan's out_of_scope_guard
"v2.0-specific test files — rewrite, never delete without v2.1
equivalent". Behaviors that survive under v2.1 stay here."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentboard.tui.app import DevBoardApp


async def _run_cmd(pilot, cmd: str) -> None:
    await pilot.press("colon")
    await pilot.pause()
    for ch in cmd:
        if ch == " ":
            await pilot.press("space")
        else:
            await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


def _bootstrap_board(tmp_path: Path, *goals) -> None:
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    for gid, title in goals:
        board.goals.append(Goal(id=gid, title=title, status=GoalStatus.active))
    store.save_board(board)


@pytest.mark.asyncio
async def test_colon_goals_focuses_resources_goals(tmp_path: Path) -> None:
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    board.goals.append(Goal(id="g_1", title="goal-one", status=GoalStatus.active))
    store.save_board(board)

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        goals_list = app.query_one("#resources-goals")

        await pilot.press("colon")
        await pilot.pause()
        cmd_line = app.query_one("#command-line")
        assert app.focused is cmd_line

        for ch in "goals":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()

        assert app.focused is goals_list, f"expected goals list focused, got {app.focused!r}"


@pytest.mark.asyncio
async def test_colon_goto_single_match_selects(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path, ("g_alpha", "alpha"), ("g_beta", "beta"))
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "goto g_al")
        assert app.board.active_goal_id == "g_alpha"


@pytest.mark.asyncio
async def test_colon_goto_ambiguous_hints(tmp_path: Path) -> None:
    """v2.1: ambiguous hint shows in command-line (not the sidebar)
    to keep GoalSideList._goal_ids in sync with ListView rows."""
    _bootstrap_board(tmp_path, ("g_alpha", "alpha"), ("g_alpine", "alpine"))
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "goto g_al")
        cl = app.query_one("#command-line")
        assert "Ambiguous" in cl.value, (
            f"ambiguous hint should be in command-line; got {cl.value!r}"
        )


@pytest.mark.asyncio
async def test_help_modal_fuzzy_tolerates_typo(tmp_path: Path) -> None:
    from agentboard.tui.help_modal import DEFAULT_ENTRIES, fuzzy_filter

    hits = fuzzy_filter(DEFAULT_ENTRIES, "dff", threshold=70)
    assert any("diff" in e.name for e in hits), f"dff should fuzzy-match diff; got {[e.name for e in hits]}"


@pytest.mark.asyncio
async def test_help_modal_opens_without_crash(tmp_path: Path) -> None:
    from agentboard.tui.help_modal import HelpModal

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause(0.2)
        assert any(isinstance(s, HelpModal) for s in app.screen_stack), (
            f"HelpModal did not mount; screen stack: "
            f"{[type(s).__name__ for s in app.screen_stack]}"
        )


@pytest.mark.asyncio
async def test_command_line_reopen_clears_stale_error_state(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path)
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "nope")
        cl = app.query_one("#command-line")
        assert "Unknown" in cl.value

        await pilot.press("colon")
        await pilot.pause()
        assert cl.value == "", f"stale error leaked into reopened input: {cl.value!r}"


@pytest.mark.asyncio
async def test_stale_error_timer_does_not_wipe_new_user_input(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path)
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "nope")
        await pilot.press("colon")
        await pilot.pause()
        for ch in "goals":
            await pilot.press(ch)
        cl = app.query_one("#command-line")
        typed = cl.value
        assert typed == "goals", f"precondition — user typed goals, got {typed!r}"
        await pilot.pause(1.1)
        assert cl.value == "goals", (
            f"stale error timer wiped user input: {cl.value!r}"
        )


@pytest.mark.asyncio
async def test_on_input_submitted_catches_arbitrary_handler_exceptions(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path)
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        app.commands.register(
            "boom", [], lambda: (_ for _ in ()).throw(RuntimeError("nope"))
        )
        await _run_cmd(pilot, "boom")
        cl = app.query_one("#command-line")
        assert cl is not None
        assert "nope" in cl.value or cl.styles.background is not None
