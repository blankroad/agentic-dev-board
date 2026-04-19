from __future__ import annotations

import json
from pathlib import Path

import pytest


def _bootstrap(tmp_path: Path, *goals: tuple[str, str], active: str | None = None) -> None:
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

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
    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "only-goal"), active="g_1")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        for wid in (
            "#status-bar-body",
            "#resources-goals",
            "#goal-side-legend",
            "#plan-body",
            "#raw-artifacts-collapsible",
            "#meta-body",
            "#files-changed-body",
            "#command-line",
        ):
            app.query_one(wid)


@pytest.mark.asyncio
async def test_colon_then_type_works_on_v21_layout(tmp_path: Path) -> None:
    from devboard.tui.app import DevBoardApp

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


@pytest.mark.asyncio
async def test_selected_iter_change_refreshes_files_pane(tmp_path: Path) -> None:
    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "one"), active="g_1")
    task_dir = tmp_path / ".devboard" / "goals" / "g_1" / "tasks" / "t_1"
    changes = task_dir / "changes"
    changes.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_1", "status": "in_progress"}))
    (changes / "iter_1.diff").write_text("+++ b/src/one.py\n")
    (changes / "iter_2.diff").write_text("+++ b/src/two.py\n")
    (task_dir / "decisions.jsonl").write_text(
        json.dumps({"iter": 1, "phase": "tdd_green"}) + "\n"
        + json.dumps({"iter": 2, "phase": "tdd_green"}) + "\n"
    )

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        app.selected_iter = 1
        await pilot.pause()
        body = app.query_one("#files-changed-body")
        assert "src/one.py" in str(body.render())
        app.selected_iter = 2
        await pilot.pause()
        body = app.query_one("#files-changed-body")
        assert "src/two.py" in str(body.render())


@pytest.mark.asyncio
async def test_help_modal_has_legend_section(tmp_path: Path) -> None:
    from devboard.tui.help_modal import DEFAULT_ENTRIES

    names = [e.name for e in DEFAULT_ENTRIES]
    assert any("pushed" in n or "legend" in n.lower() for n in names), (
        f"HelpModal DEFAULT_ENTRIES must include goal status legend entries; got {names}"
    )


@pytest.mark.asyncio
async def test_v20_commands_still_dispatch(tmp_path: Path) -> None:
    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_xyz", "one"), active="g_xyz")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # Should NOT raise
        app.commands.dispatch("goto g_xy")


@pytest.mark.asyncio
async def test_all_v20_commands_dispatch_without_crash(tmp_path: Path) -> None:
    """Red-team: :runs/:diff/:decisions/:learn referenced v2.0-only
    widgets (#resources-runs, #context-viewer) that v2.1 removed. All
    4 raised NoMatches from their handlers. Each command must now either
    update v2.1 state or surface a friendly message — never propagate."""
    from devboard.tui.app import DevBoardApp

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

    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore
    from devboard.tui.app import DevBoardApp

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
        before = str(app.query_one("#plan-body").content.markup)
        assert "BETA_PLAN" in before, f"precondition: beta should be initial; got {before!r}"
        app.commands.dispatch("goto g_alpha")
        await pilot.pause()
        after = str(app.query_one("#plan-body").content.markup)
        assert "ALPHA_PLAN" in after, (
            f"goto must refresh PlanMarkdown to new goal's plan; still showing {after!r}"
        )


@pytest.mark.asyncio
async def test_decisions_cmd_refreshes_activity_timeline(tmp_path: Path) -> None:
    """Red-team r2 HIGH: :decisions t_other must refresh ActivityTimeline
    rows to the target task's decisions. Current bug: timeline composed
    once with initial task_id and never re-reads."""
    from devboard.tui.activity_row import ActivityRow
    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "g"), active="g_1")
    goal_dir = tmp_path / ".devboard" / "goals" / "g_1"
    for tid, phases in [("t_init", ["p_init"]), ("t_other", ["p_other_a", "p_other_b"])]:
        td = goal_dir / "tasks" / tid
        td.mkdir(parents=True)
        (td / "task.json").write_text(json.dumps({"id": tid, "status": "in_progress"}))
        (td / "decisions.jsonl").write_text(
            "\n".join(
                json.dumps({"iter": i, "phase": p}) for i, p in enumerate(phases)
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
        phases_before = sorted(
            str(r.entry.get("phase")) for r in app.query(ActivityRow).results()
        )
        assert phases_before == ["p_init"], f"precondition: {phases_before}"
        app.commands.dispatch("decisions t_other")
        await pilot.pause()
        phases_after = sorted(
            str(r.entry.get("phase")) for r in app.query(ActivityRow).results()
        )
        assert "p_other_a" in phases_after and "p_other_b" in phases_after, (
            f"decisions must refresh ActivityTimeline; got {phases_after}"
        )


@pytest.mark.asyncio
async def test_clicking_activity_row_navigates_to_that_iter(tmp_path: Path) -> None:
    """Clicking a timeline entry should jump Meta/Files to that iter —
    otherwise the timeline is display-only and users have no way to drill
    into a specific event."""
    from devboard.tui.activity_row import ActivityRow
    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "g"), active="g_1")
    task_dir = tmp_path / ".devboard" / "goals" / "g_1" / "tasks" / "t_1"
    changes = task_dir / "changes"
    changes.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_1", "status": "in_progress"}))
    (task_dir / "decisions.jsonl").write_text(
        "\n".join(
            json.dumps({"iter": i, "phase": "tdd_green"}) for i in (1, 2, 3)
        )
        + "\n"
    )
    (changes / "iter_1.diff").write_text("+++ b/src/one.py\n")
    (changes / "iter_2.diff").write_text("+++ b/src/two.py\n")
    (changes / "iter_3.diff").write_text("+++ b/src/three.py\n")

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # expand timeline so rows receive clicks
        await pilot.press("h")
        await pilot.pause()
        rows = list(app.query(ActivityRow).results())
        # find the iter=1 row (newest-first means rows[-1])
        iter_one_row = next(r for r in rows if r.entry.get("iter") == 1)
        await pilot.click(iter_one_row)
        await pilot.pause()
        assert app.selected_iter == 1, (
            f"click on iter 1 row must set selected_iter; got {app.selected_iter}"
        )
        body = app.query_one("#files-changed-body")
        assert "src/one.py" in str(body.render()), (
            "FilesChanged pane must refresh to clicked iter"
        )


@pytest.mark.asyncio
async def test_clicking_goal_sidebar_entry_switches_goal(tmp_path: Path) -> None:
    """Clicking a goal in the sidebar should navigate to it — same as
    running ':goto <id>'. Otherwise the list is read-only decoration."""
    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_first", "first"), ("g_second", "second"), active="g_first")
    for gid in ("g_first", "g_second"):
        (tmp_path / ".devboard" / "goals" / gid / "plan.md").write_text(f"# PLAN_{gid}\n")

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # initial active goal
        assert app.board.active_goal_id == "g_first"
        lv = app.query_one("#resources-goals")
        # click the second ListItem
        second_item = list(lv.children)[1]
        await pilot.click(second_item)
        await pilot.pause()
        assert app.board.active_goal_id == "g_second", (
            f"click on sidebar goal must switch active; got {app.board.active_goal_id}"
        )


@pytest.mark.asyncio
async def test_plan_toc_line_shows_h2_headings(tmp_path: Path) -> None:
    """Spec: above the ActivityTimeline, a '#plan-toc' line lists the
    active plan's H2 section titles so the user can see structure without
    scrolling the plan pane."""
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore
    from devboard.tui.app import DevBoardApp

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_toc")
    board.goals.append(Goal(id="g_toc", title="g", status=GoalStatus.active))
    store.save_board(board)
    gd = tmp_path / ".devboard" / "goals" / "g_toc"
    gd.mkdir(parents=True)
    (gd / "plan_summary.md").write_text(
        "# Title\n\n## Problem\n\ntext\n\n## Architecture\n\nmore\n\n## Goal Checklist\n\n- a\n"
    )

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        toc = app.query_one("#plan-toc")
        text = str(toc.render())
        for section in ("Problem", "Architecture", "Goal Checklist"):
            assert section in text, f"TOC missing {section}; got {text!r}"


@pytest.mark.asyncio
async def test_h_key_toggles_activity_timeline(tmp_path: Path) -> None:
    """Spec: pressing 'h' anywhere (outside CommandLine Input) toggles
    ActivityTimeline's collapsed state. Convenient shortcut for 'history'."""
    from textual.widgets import Collapsible

    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "g"), active="g_1")
    task_dir = tmp_path / ".devboard" / "goals" / "g_1" / "tasks" / "t_1"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_1", "status": "in_progress"}))
    (task_dir / "decisions.jsonl").write_text(
        json.dumps({"iter": 1, "phase": "tdd_green"}) + "\n"
    )

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        col = app.query_one("#activity-collapsible", Collapsible)
        assert col.collapsed is True
        await pilot.press("h")
        await pilot.pause()
        assert col.collapsed is False, "'h' should expand the timeline"
        await pilot.press("h")
        await pilot.pause()
        assert col.collapsed is True, "'h' pressed again should collapse"


@pytest.mark.asyncio
async def test_runs_list_not_in_layout(tmp_path: Path) -> None:
    from textual.css.query import NoMatches

    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "one"), active="g_1")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        with pytest.raises(NoMatches):
            app.query_one("#resources-runs")
