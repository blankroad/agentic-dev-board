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
            "#gauntlet-collapsible",
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
async def test_runs_list_not_in_layout(tmp_path: Path) -> None:
    from textual.css.query import NoMatches

    from devboard.tui.app import DevBoardApp

    _bootstrap(tmp_path, ("g_1", "one"), active="g_1")
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        with pytest.raises(NoMatches):
            app.query_one("#resources-runs")
