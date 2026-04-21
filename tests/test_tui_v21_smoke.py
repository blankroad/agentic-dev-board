from __future__ import annotations

import json
from pathlib import Path

import pytest


def _bootstrap(tmp_path: Path, *goals: tuple[str, str], active: str | None = None) -> None:
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id=active)
    for gid, title in goals:
        board.goals.append(Goal(id=gid, title=title, status=GoalStatus.active))
    store.save_board(board)
    for gid, _ in goals:
        (tmp_path / ".devboard" / "goals" / gid).mkdir(parents=True, exist_ok=True)
        (tmp_path / ".devboard" / "goals" / gid / "plan.md").write_text("# p\n")


@pytest.mark.asyncio
async def test_app_mounts_v21_layout_and_all_panes_exist(tmp_path: Path) -> None:
    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "only-goal"), active="g_1")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # v2.3: right column removed. Center col is a single #phase-flow
        # (5-tab) whose TabPane bodies are wrapped in VerticalScroll.
        for wid in (
            "#status-bar-body",
            "#resources-goals",
            "#goal-side-legend",
            "#phase-flow",
            "#plan-body",
            "#command-line",
        ):
            app.query_one(wid)


@pytest.mark.asyncio
async def test_colon_then_type_works_on_v21_layout(tmp_path: Path) -> None:
    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "goal-one"), active="g_1")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await pilot.press("colon")
        await pilot.pause()
        for ch in "goto":
            await pilot.press(ch)
        await pilot.pause()
        cl = app.query_one("#command-line")
        assert cl.value == "goto", f"typing failed; got {cl.value!r}"


# v2.3: test_selected_iter_change_refreshes_files_pane removed — it
# asserted on #files-changed-body which belonged to the deleted
# FilesChangedPane. Right-panel redesign goal g_20260420_203952_f98d46
# absorbed this cleanup.


@pytest.mark.asyncio
async def test_help_modal_has_legend_section(tmp_path: Path) -> None:
    from agentboard.tui.help_modal import DEFAULT_ENTRIES

    names = [e.name for e in DEFAULT_ENTRIES]
    assert any("pushed" in n or "legend" in n.lower() for n in names), (
        f"HelpModal DEFAULT_ENTRIES must include goal status legend entries; got {names}"
    )


@pytest.mark.asyncio
async def test_v20_commands_still_dispatch(tmp_path: Path) -> None:
    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_xyz", "one"), active="g_xyz")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # Should NOT raise
        app.commands.dispatch("goto g_xy")


@pytest.mark.asyncio
async def test_live_status_line_shows_latest_event_at_bottom(tmp_path: Path) -> None:
    """A 1-line LiveStatusLine sits above the CommandLine and shows the
    most recent formatted event from runs/*.jsonl. Complements StatusBar
    (top = goal context, bottom = raw live feed)."""
    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "g"), active="g_1")
    runs_dir = tmp_path / ".devboard" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_file = runs_dir / "run_live.jsonl"
    run_file.write_text("")

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # Widget exists
        line = app.query_one("#live-status-line")
        # Append new event
        run_file.write_text(
            json.dumps(
                {
                    "ts": "2026-04-19T15:16:17+00:00",
                    "event": "tdd_green_complete",
                    "state": {"iteration": 5, "status": "GREEN_CONFIRMED"},
                }
            )
            + "\n"
        )
        for _ in range(20):
            await pilot.pause(0.1)
            body = app.query_one("#live-status-body")
            if "15:16:17" in str(body.render()):
                break
        body = app.query_one("#live-status-body")
        rendered = str(body.render())
        assert "15:16:17" in rendered, rendered
        assert "tdd_green_complete" in rendered, rendered


@pytest.mark.asyncio
async def test_all_v20_commands_dispatch_without_crash(tmp_path: Path) -> None:
    """Red-team: :runs/:diff/:decisions/:learn referenced v2.0-only
    widgets (#resources-runs, #context-viewer) that v2.1 removed. All
    4 raised NoMatches from their handlers. Each command must now either
    update v2.1 state or surface a friendly message — never propagate."""
    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "one"), active="g_1")
    task_dir = tmp_path / ".devboard" / "goals" / "g_1" / "tasks" / "t_1"
    changes = task_dir / "changes"
    changes.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_1", "status": "in_progress"}))
    (changes / "iter_1.diff").write_text("+++ b/src/x.py\n")
    (task_dir / "decisions.jsonl").write_text(
        json.dumps({"iter": 1, "phase": "tdd_green"}) + "\n"
    )

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        for cmd in ["runs", "diff t_1", "decisions t_1", "learn hello"]:
            # Must NOT raise
            app.commands.dispatch(cmd)


@pytest.mark.asyncio
async def test_goto_refreshes_plan_markdown_to_new_goal(tmp_path: Path) -> None:
    """Red-team r2 CRITICAL: SessionContext.active_goal_id is a cached
    disk-mtime lookup that ignores app._board.active_goal_id. After :goto
    switches the board's active goal, PlanMarkdown must re-render to the
    new goal's plan.md — not stay on the original goal."""
    import os
    import time

    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore
    from agentboard.tui.app import DevBoardApp

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_alpha")
    board.goals.append(Goal(id="g_alpha", title="alpha-goal", status=GoalStatus.active))
    board.goals.append(Goal(id="g_beta", title="beta-goal", status=GoalStatus.active))
    store.save_board(board)
    for gid, plan in [("g_alpha", "# ALPHA_PLAN\n"), ("g_beta", "# BETA_PLAN\n")]:
        d = tmp_path / ".devboard" / "goals" / gid
        d.mkdir(parents=True)
        (d / "plan.md").write_text(plan)
    # Make alpha's plan older so beta is auto-active on mount.
    old = time.time() - 1000
    os.utime(tmp_path / ".devboard" / "goals" / "g_alpha" / "plan.md", (old, old))

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow")
        before = flow.plan_body_text()
        assert "BETA_PLAN" in before, f"precondition: beta should be initial; got {before!r}"
        app.commands.dispatch("goto g_alpha")
        await pilot.pause()
        after = flow.plan_body_text()
        assert "ALPHA_PLAN" in after, (
            f"goto must refresh PhaseFlowView Plan tab to new goal's plan; still showing {after!r}"
        )


@pytest.mark.asyncio
async def test_decisions_cmd_refreshes_phase_flow(tmp_path: Path) -> None:
    """v2.2 (was: Red-team r2 HIGH): :decisions t_other must refresh
    PhaseFlowView Dev tab to the target task's decisions. Timeline was
    replaced by the Dev tab inside PhaseFlowView; the refresh contract
    (command re-reads per-task state) must survive the swap."""
    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "g"), active="g_1")
    goal_dir = tmp_path / ".devboard" / "goals" / "g_1"
    # Use dev-phase names so they route into the Dev tab body. (Review
    # phases would land in Review tab instead.)
    for tid, phases in [
        ("t_init", ["tdd_init"]),
        ("t_other", ["tdd_other_a", "tdd_other_b"]),
    ]:
        td = goal_dir / "tasks" / tid
        td.mkdir(parents=True)
        (td / "task.json").write_text(json.dumps({"id": tid, "status": "in_progress"}))
        (td / "decisions.jsonl").write_text(
            "\n".join(
                json.dumps({"iter": i, "phase": p, "verdict_source": p.upper()})
                for i, p in enumerate(phases)
            )
            + "\n"
        )
    # Make t_init newer so it is chosen as initial
    import os
    import time

    old = time.time() - 1000
    os.utime(goal_dir / "tasks" / "t_other", (old, old))

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow")
        before = flow.dev_body_text()
        assert "TDD_INIT" in before, f"precondition: dev body should show t_init; got {before!r}"
        app.commands.dispatch("decisions t_other")
        await pilot.pause()
        after = flow.dev_body_text()
        assert "TDD_OTHER_A" in after and "TDD_OTHER_B" in after, (
            f"decisions must refresh Dev tab; got {after!r}"
        )


# v2.2: `test_clicking_activity_row_navigates_to_that_iter` removed —
# ActivityRow + ActivityTimeline replaced by PhaseFlowView's Dev tab.
# Click-to-select-iter belongs to the right-panel redesign (separate goal).


@pytest.mark.asyncio
async def test_goto_ambiguous_does_not_desync_sidebar_click_mapping(tmp_path: Path) -> None:
    """Red-team r3 HIGH: goto_cmd used to append 'Ambiguous'/'No match'
    labels directly to the goals ListView, leaving GoalSideList._goal_ids
    stale. Subsequent clicks mapped to the ORIGINAL goals, not the
    labels the user saw. After fix: goto ambiguous shows hint in command
    line, sidebar stays in sync with _goal_ids so click always navigates
    to the labeled goal."""
    from agentboard.tui.app import DevBoardApp

    _bootstrap(
        tmp_path,
        ("g_alpha", "alpha"),
        ("g_bravo", "bravo"),
        ("g_charlie", "charlie"),
        active="g_alpha",
    )
    for gid in ("g_alpha", "g_bravo", "g_charlie"):
        (tmp_path / ".devboard" / "goals" / gid / "plan.md").write_text(f"# {gid}\n")

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # Ambiguous goto
        app.commands.dispatch("goto g_")
        await pilot.pause()
        lv = app.query_one("#resources-goals")
        items = list(lv.children)
        gsl = app.query_one("#goal-side-list")
        # Sidebar must stay in sync: one item per tracked goal_id, nothing
        # extra (no 'Ambiguous' label stuffed in), no missing
        assert len(items) == len(gsl._goal_ids), (
            f"sidebar/_goal_ids mismatch: items={len(items)} "
            f"ids={gsl._goal_ids}"
        )
        # Click item[0] → navigate to _goal_ids[0]. Must equal the goal
        # labeled on that row (no surprise swap).
        labels = [
            str(item.query_one("Label").render()) for item in items
        ]
        await pilot.click(items[0])
        await pilot.pause()
        # The first goal_id in the sidebar corresponds to the first label.
        # Whatever goal got activated must match label[0]'s text.
        activated = app.board.active_goal_id
        assert activated is not None
        assert activated in labels[0] or labels[0].endswith(
            next(
                g["title"]
                for g in app.session.all_goals()
                if g["id"] == activated
            )
        ), (
            f"click on labeled row must navigate to the displayed goal. "
            f"label={labels[0]!r} activated={activated}"
        )


@pytest.mark.asyncio
async def test_clicking_goal_sidebar_entry_switches_goal(tmp_path: Path) -> None:
    """Clicking a goal in the sidebar should navigate to it — same as
    running ':goto <id>'. Otherwise the list is read-only decoration."""
    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_first", "first"), ("g_second", "second"), active="g_first")
    for gid in ("g_first", "g_second"):
        (tmp_path / ".devboard" / "goals" / gid / "plan.md").write_text(f"# PLAN_{gid}\n")

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # initial active goal
        assert app.board.active_goal_id == "g_first"
        lv = app.query_one("#resources-goals")
        # Sidebar now sorts roots by created_at desc, so index is not
        # insertion-order. Locate the 'second' entry by label text.
        target_item = None
        for item in lv.children:
            try:
                text = str(item.query_one("Label").render())
            except Exception:
                continue
            if "second" in text:
                target_item = item
                break
        assert target_item is not None, "sidebar missing 'second' goal"
        await pilot.click(target_item)
        await pilot.pause()
        assert app.board.active_goal_id == "g_second", (
            f"click on sidebar goal must switch active; got {app.board.active_goal_id}"
        )


# v2.2: `test_plan_toc_line_shows_h2_headings` removed — #plan-toc Static
# is superseded by the 4-tab header of PhaseFlowView (tabs ARE the TOC).
# Navigation covered by test_number_key_two_activates_dev_tab in
# tests/test_tui_phase_flow.py.

# v2.2: `test_h_key_toggles_activity_timeline` removed — 'h' binding
# deleted along with ActivityTimeline. Equivalent navigation uses number
# keys 1/2/3/4 (tested in tests/test_tui_phase_flow.py).


@pytest.mark.asyncio
async def test_runs_list_not_in_layout(tmp_path: Path) -> None:
    from textual.css.query import NoMatches

    from agentboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "one"), active="g_1")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        with pytest.raises(NoMatches):
            app.query_one("#resources-runs")
