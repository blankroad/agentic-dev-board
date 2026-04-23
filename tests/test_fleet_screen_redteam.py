"""FleetScreen redteam-fix tests (M2-fleet-tui iter 10).

Each test encodes one redteam finding from the BROKEN verdict:
- CRITICAL #1 (F double-push): idempotent action_open_fleet
- CRITICAL #2 (r replay dead key): action_replay_selected notifies on unknown command
- HIGH #3 (destructive k): action_kill_selected requires confirmation, uses GoalStatus enum
- HIGH #4 (filter Input trap): Escape dismisses filter without submit
- HIGH #5 (unconditional pop): on_goal_activated guards on FleetScreen top

guards: pilot-test-must-not-mask-default-focus-bug — all Pilot flows
use real key presses without .focus() cheats.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    dev = tmp_path / ".agentboard"
    (dev / "goals" / "g_alpha" / "tasks" / "t_a").mkdir(parents=True)
    (dev / "goals" / "g_beta" / "tasks" / "t_b").mkdir(parents=True)
    (dev / "runs").mkdir(parents=True)
    board = {
        "version": 1,
        "board_id": "b_test",
        "active_goal_id": "g_alpha",
        "goals": [
            {"id": "g_alpha", "title": "Alpha", "status": "active", "task_ids": ["t_a"],
             "created_at": "2026-04-22T00:00:00+00:00",
             "updated_at": "2026-04-22T00:00:00+00:00"},
            {"id": "g_beta", "title": "Beta", "status": "active", "task_ids": ["t_b"],
             "created_at": "2026-04-22T00:00:00+00:00",
             "updated_at": "2026-04-22T00:00:00+00:00"},
        ],
        "updated_at": "2026-04-22T00:00:00+00:00",
    }
    (dev / "state.json").write_text(json.dumps(board))
    for gid in ("g_alpha", "g_beta"):
        (dev / "goals" / gid / "goal.json").write_text(json.dumps({
            "id": gid, "title": gid.replace("g_", "").title(),
            "description": "", "status": "active", "branch_prefix": "", "task_ids": [],
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        }))
    return tmp_path


async def test_f_binding_is_idempotent_no_double_push(tmp_project: Path) -> None:
    """CRITICAL #1: pressing F while FleetScreen is already on top must NOT double-push."""
    from agentboard.tui.app import AgentBoardApp
    from agentboard.tui.fleet_screen import FleetScreen

    app = AgentBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.press("F")
        await pilot.pause()
        assert isinstance(app.screen, FleetScreen)
        stack_after_first = len(app.screen_stack)

        await pilot.press("F")
        await pilot.pause()
        # Stack depth unchanged — second F is a no-op or refresh, not push
        assert len(app.screen_stack) == stack_after_first, (
            f"F double-push detected: stack grew from {stack_after_first} "
            f"to {len(app.screen_stack)}"
        )


async def test_r_replay_surfaces_feedback_when_no_handler(tmp_project: Path) -> None:
    """CRITICAL #2: r must NOT be a silent no-op — surface feedback via app.notify."""
    from agentboard.tui.app import AgentBoardApp

    app = AgentBoardApp(store_root=tmp_project)
    notifications: list[str] = []

    async with app.run_test() as pilot:
        # Intercept notify to capture the feedback
        orig_notify = app.notify

        def _capture_notify(message, **kwargs):
            notifications.append(str(message))
            return orig_notify(message, **kwargs)

        app.notify = _capture_notify  # type: ignore[assignment]

        await pilot.press("F")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

    # At least one notify call mentioning replay / not-implemented / etc.
    assert any(
        "replay" in n.lower() for n in notifications
    ), f"expected replay feedback, got notifications: {notifications}"


async def test_k_kill_requires_confirmation_and_uses_enum(tmp_project: Path) -> None:
    """HIGH #3: k must not mutate on single keypress; after confirmation, status is GoalStatus enum."""
    from agentboard.models import GoalStatus
    from agentboard.tui.app import AgentBoardApp
    from agentboard.storage.file_store import FileStore

    def _find(board, gid):
        for g in board.goals:
            if g.id == gid:
                return g
        return None

    app = AgentBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.press("F")
        await pilot.pause()
        await pilot.press("k")
        await pilot.pause()

        # the selected (first) row is whatever the aggregator ordered first
        target_gid = app.screen._pending_kill_gid
        assert target_gid is not None, "k must arm a pending kill"

        # k alone must NOT mutate
        store = FileStore(tmp_project)
        board = store.load_board()
        g = _find(board, target_gid)
        assert g is not None and g.status == GoalStatus.active, (
            f"k mutated status without confirmation: target={target_gid} got={g.status if g else 'missing'}"
        )

        # confirm via y to finalize kill
        await pilot.press("y")
        await pilot.pause()

        board2 = store.load_board()
        g2 = _find(board2, target_gid)
        assert g2 is not None
        assert g2.status == GoalStatus.blocked
        assert isinstance(g2.status, GoalStatus)


async def test_filter_input_escape_dismisses_without_submit(tmp_project: Path) -> None:
    """HIGH #4: Escape in filter Input restores focus to pane; filter stays empty."""
    from agentboard.tui.app import AgentBoardApp
    from agentboard.tui.fleet_view import FleetListPane

    app = AgentBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.press("F")
        await pilot.pause()
        await pilot.press("slash")
        await pilot.pause()
        # type a char
        await pilot.press("a")
        await pilot.pause()
        # escape
        await pilot.press("escape")
        await pilot.pause()

        pane = app.screen.query_one(FleetListPane)
        assert pane._filter_query == "", (
            f"escape should not apply filter, got filter_query={pane._filter_query!r}"
        )
        # Focus restored: pressing down navigates rows
        start = pane.selected_index
        await pilot.press("down")
        await pilot.pause()
        assert pane.selected_index != start or start == 1, (
            "focus was not restored to pane after escape"
        )


async def test_on_goal_activated_guards_wrong_screen(tmp_project: Path) -> None:
    """HIGH #5: on_goal_activated must not pop if FleetScreen is not on top."""
    from agentboard.tui.app import AgentBoardApp
    from agentboard.tui.fleet_screen import GoalActivated

    app = AgentBoardApp(store_root=tmp_project)
    async with app.run_test() as pilot:
        await pilot.pause()
        # FleetScreen NOT on stack — simulate a stray GoalActivated arriving
        # (e.g. from a delayed bubble after another modal pushed on top)
        depth_before = len(app.screen_stack)
        msg = GoalActivated(goal_id="g_alpha")
        app.post_message(msg)
        await pilot.pause()
        # Must NOT pop the main screen
        assert len(app.screen_stack) >= depth_before, (
            f"on_goal_activated popped main screen: {depth_before} → "
            f"{len(app.screen_stack)}"
        )
