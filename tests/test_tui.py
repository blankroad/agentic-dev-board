from __future__ import annotations

from pathlib import Path

import pytest

from devboard.models import BoardState, Goal, GoalStatus
from devboard.storage.file_store import FileStore
from devboard.tui.app_legacy import DevBoardApp
from devboard.tui.gauntlet_view import GauntletView


# ── Gauntlet step state machine ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gauntlet_view_steps(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    store.save_board(board)

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        gv = app.query_one("#gauntlet-view", GauntletView)

        # Initially all pending
        assert gv.step_statuses == ["pending"] * 5

        # Set step 0 running
        gv.set_step_running(0)
        assert gv.step_statuses[0] == "running"
        assert all(s == "pending" for s in gv.step_statuses[1:])

        # Set step 0 done, step 1 running
        gv.set_step_running(1)
        assert gv.step_statuses[0] == "done"
        assert gv.step_statuses[1] == "running"

        # Set all done
        gv.set_all_done()
        assert all(s == "done" for s in gv.step_statuses)

        # Reset
        gv.reset()
        assert all(s == "pending" for s in gv.step_statuses)


# ── Board renders goals ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_board_view_renders_goals(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    goal = Goal(title="Test Goal Alpha", description="Build something")
    board.goals.append(goal)
    board.active_goal_id = goal.id
    store.save_board(board)
    store.save_goal(goal)

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        # The board view should be mounted
        from devboard.tui.board_view import BoardView
        bv = app.query_one("#board-view", BoardView)
        from textual.widgets import DataTable
        table = bv.query_one("#goal-table", DataTable)
        assert table.row_count == 1


# ── App starts without error ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_app_starts(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    store.save_board(board)

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        # Header is present
        from textual.widgets import Header
        assert app.query(Header)

        # Both tabs exist
        from textual.widgets import TabbedContent
        tabs = app.query_one("#main-tabs", TabbedContent)
        assert tabs is not None

        # Can switch to log tab
        await pilot.press("f2")
        await pilot.pause()
        assert tabs.active == "log"

        # Back to board
        await pilot.press("f1")
        await pilot.pause()
        assert tabs.active == "board"


# ── Log view accepts writes ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_view_writes(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    store.save_board(board)

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        from devboard.tui.log_view import LogView
        lv = app.query_one("#log-view", LogView)
        lv.write_step("Plan", "step 1: create hello.py")
        lv.write_verdict("PASS", 1)
        lv.write_tool("fs_write", "Written 42 bytes", error=False)
        # No assertion on content — just verifying no exceptions raised


# ── Goal selection updates task view ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_goal_selection_updates_task_view(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    goal = Goal(title="Calculator Goal", description="build calc.py")
    board.goals.append(goal)
    store.save_board(board)
    store.save_goal(goal)

    from devboard.gauntlet.lock import build_locked_plan
    plan = build_locked_plan(goal.id, {
        "problem": "Build calculator",
        "non_goals": [],
        "scope_decision": "HOLD",
        "architecture": "single calc.py",
        "known_failure_modes": [],
        "goal_checklist": ["add() works", "div-by-zero raises"],
        "out_of_scope_guard": [],
        "token_ceiling": 50000,
        "max_iterations": 3,
    })
    store.save_locked_plan(plan)

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        # Simulate goal selection
        app._on_goal_selected(goal.id)
        await pilot.pause()

        from devboard.tui.task_view import TaskView
        from textual.widgets import Static as TStatic
        tv = app.query_one("#task-view", TaskView)
        title_widget = tv.query_one("#task-title", TStatic)
        assert title_widget is not None
