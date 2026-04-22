"""FleetScreen Pilot tests — real-user-flow, without explicit focus
(M2-fleet-tui s_006–s_009).

guards: pilot-test-must-not-mask-default-focus-bug
        (learnings/pilot-test-must-not-mask-default-focus-bug.md)

Every test drives the app through DevBoardApp's F binding and then
presses keys as the user would, WITHOUT calling .focus() on the
widget under test. This mirrors the real TTY boot path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """A .devboard fixture with two goals so Fleet has rows to show."""
    dev = tmp_path / ".devboard"
    (dev / "goals" / "g_alpha" / "tasks" / "t_a").mkdir(parents=True)
    (dev / "goals" / "g_beta" / "tasks" / "t_b").mkdir(parents=True)
    (dev / "runs").mkdir(parents=True)
    board = {
        "version": 1,
        "board_id": "b_test",
        "active_goal_id": "g_alpha",
        "goals": [
            {
                "id": "g_alpha", "title": "Alpha", "status": "active",
                "task_ids": ["t_a"], "created_at": "2026-04-22T00:00:00+00:00",
                "updated_at": "2026-04-22T00:00:00+00:00",
            },
            {
                "id": "g_beta", "title": "Beta", "status": "active",
                "task_ids": ["t_b"], "created_at": "2026-04-22T00:00:00+00:00",
                "updated_at": "2026-04-22T00:00:00+00:00",
            },
        ],
        "updated_at": "2026-04-22T00:00:00+00:00",
    }
    (dev / "board.json").write_text(json.dumps(board))
    for gid in ("g_alpha", "g_beta"):
        goal_json = {
            "id": gid, "title": gid.replace("g_", "").title(),
            "description": "", "status": "active", "branch_prefix": "",
            "task_ids": [], "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        }
        (dev / "goals" / gid / "goal.json").write_text(json.dumps(goal_json))
    return tmp_path


async def test_fleet_screen_mount_focuses_list_pane(tmp_project: Path) -> None:
    """s_006: FleetScreen mount explicitly focuses FleetListPane so ↓ reaches it."""
    from agentboard.tui.app import DevBoardApp
    from agentboard.tui.fleet_screen import FleetScreen
    from agentboard.tui.fleet_view import FleetListPane

    app = DevBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.press("F")
        await pilot.pause()
        assert isinstance(app.screen, FleetScreen)
        focused = app.screen.focused
        assert isinstance(focused, FleetListPane), (
            f"expected FleetListPane focused, got {type(focused).__name__}"
        )


async def test_fleet_screen_real_user_flow_f_down_without_explicit_focus(
    tmp_project: Path,
) -> None:
    """s_007: F opens, down moves selection WITHOUT any .focus() cheat."""
    from agentboard.tui.app import DevBoardApp
    from agentboard.tui.fleet_view import FleetListPane

    app = DevBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.press("F")
        await pilot.pause()
        pane = app.screen.query_one(FleetListPane)
        start = pane.selected_index
        await pilot.press("down")
        await pilot.pause()
        # With 2 goals in fixture, down should move from 0 → 1
        assert start == 0
        assert pane.selected_index == 1


async def test_fleet_screen_enter_activates_goal_and_pops(tmp_project: Path) -> None:
    """s_008: Enter on a row pops FleetScreen + sets session.active_goal_id."""
    from agentboard.tui.app import DevBoardApp
    from agentboard.tui.fleet_screen import FleetScreen

    app = DevBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.press("F")
        await pilot.pause()
        # Move to second row then activate
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Screen should be popped (no FleetScreen on top)
        assert not isinstance(app.screen, FleetScreen)
        # active_goal_id updated to g_beta (second row alphabetical)
        assert app.session.active_goal_id == "g_beta"


async def test_fleet_screen_unmount_cancels_tail_interval(tmp_project: Path) -> None:
    """s_009: on_unmount cancels the tail-worker interval timer."""
    from agentboard.tui.app import DevBoardApp
    from agentboard.tui.fleet_screen import FleetScreen

    app = DevBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.press("F")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FleetScreen)
        timer = screen._tail_timer
        assert timer is not None
        # Pop via q
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, FleetScreen)
        # Timer should be stopped (Textual Timer._active flips, or is cancelled)
        # We assert the screen no longer holds a live timer reference.
        assert screen._tail_timer is None or timer._active is False
