from __future__ import annotations

from pathlib import Path

import pytest

from devboard.tui.app import DevBoardApp


@pytest.mark.asyncio
async def test_app_launches_with_empty_devboard_shows_empty_state(tmp_path: Path) -> None:
    from textual.widgets import Static

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        body = app.query_one("#live-stream-body", Static)
        assert "No devboard state" in str(body.render())


@pytest.mark.asyncio
async def test_colon_goals_focuses_resources_goals(tmp_path: Path) -> None:
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

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
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState()
    for gid, title in goals:
        board.goals.append(Goal(id=gid, title=title, status=GoalStatus.active))
    store.save_board(board)


@pytest.mark.asyncio
async def test_colon_runs_populates_runs_list(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path)
    runs_dir = tmp_path / ".devboard" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "run_alpha.jsonl").write_text('{"event": "run_start", "state": {}}\n')

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "runs")
        runs_list = app.query_one("#resources-runs")
        # Must contain at least one rendered item
        assert runs_list.children, "runs list should have populated children"


@pytest.mark.asyncio
async def test_colon_diff_loads_diff_tab(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path, ("g_1", "goal-one"))
    changes = tmp_path / ".devboard" / "goals" / "g_1" / "tasks" / "t_abc" / "changes"
    changes.mkdir(parents=True)
    (changes / "iter_1.diff").write_text("+++ added line\n")

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "diff t_abc")
        body = app.query_one("#tab-diff-body")
        assert "added line" in str(body.render())


@pytest.mark.asyncio
async def test_colon_decisions_loads_decisions_tab(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path, ("g_1", "goal-one"))
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "decisions t_missing")
        body = app.query_one("#tab-decisions-body")
        assert "No decisions" in str(body.render())


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
    _bootstrap_board(tmp_path, ("g_alpha", "alpha"), ("g_alpine", "alpine"))
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "goto g_al")
        goals_list = app.query_one("#resources-goals")
        rendered = " ".join(str(c.query_one("Label").render()) for c in goals_list.children if hasattr(c, "query_one"))
        assert "Ambiguous" in rendered


@pytest.mark.asyncio
async def test_colon_learn_renders_results(tmp_path: Path) -> None:
    _bootstrap_board(tmp_path)
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await _run_cmd(pilot, "learn nonexistent")
        body = app.query_one("#tab-learnings-body")
        assert "No learnings" in str(body.render()) or "Search failed" in str(body.render())


@pytest.mark.asyncio
async def test_number_keys_switch_context_tabs(tmp_path: Path) -> None:
    from textual.widgets import TabbedContent

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # No focus setup — App BINDINGS for "1".."5" fire when nothing claims them.
        await pilot.press("3")
        await pilot.pause()
        tabs = app.query_one("#context-tabs", TabbedContent)
        assert tabs.active == "tab-learnings"


@pytest.mark.asyncio
async def test_help_modal_fuzzy_tolerates_typo(tmp_path: Path) -> None:
    from devboard.tui.help_modal import DEFAULT_ENTRIES, fuzzy_filter

    # Unit-level: typo 'dff' still matches 'diff' commands via partial_ratio >= 70
    hits = fuzzy_filter(DEFAULT_ENTRIES, "dff", threshold=70)
    assert any("diff" in e.name for e in hits), f"dff should fuzzy-match diff; got {[e.name for e in hits]}"


@pytest.mark.asyncio
async def test_context_viewer_diff_tab_default_is_action_prompt(tmp_path: Path) -> None:
    """Placeholders like '(diff)' teach nothing. Each tab must tell the
    user what to type to populate it."""
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        body = app.query_one("#tab-diff-body")
        text = str(body.render())
        assert ":diff" in text, f"diff tab should hint at :diff command; got {text!r}"


@pytest.mark.asyncio
async def test_context_viewer_plan_tab_loads_active_goal_plan(tmp_path: Path) -> None:
    """If there is an active goal with a plan.md, the Plan tab should
    show the plan on launch — not a placeholder."""
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    board = BoardState(active_goal_id="g_test")
    board.goals.append(Goal(id="g_test", title="my-goal", status=GoalStatus.active))
    store.save_board(board)
    plan_dir = tmp_path / ".devboard" / "goals" / "g_test"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan.md").write_text("# Plan for my-goal\n\nStep 1: do thing\n")

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        body = app.query_one("#tab-plan-body")
        text = str(body.render())
        assert "my-goal" in text or "Step 1" in text, (
            f"Plan tab should load active goal's plan.md; got {text!r}"
        )


@pytest.mark.asyncio
async def test_live_stream_renders_human_line_not_raw_json(tmp_path: Path) -> None:
    """LiveStream currently dumps raw JSON. Surface a human line via
    format_event_line so users can scan events at a glance."""
    import json

    _bootstrap_board(tmp_path, ("g_1", "goal-one"))
    runs_dir = tmp_path / ".devboard" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_file = runs_dir / "run_fmt.jsonl"
    run_file.write_text(
        json.dumps(
            {
                "ts": "2026-04-19T10:11:12+00:00",
                "event": "tdd_green_complete",
                "state": {"iteration": 2, "status": "GREEN_CONFIRMED"},
            }
        )
        + "\n"
    )

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        for _ in range(20):
            await pilot.pause(0.1)
            body = app.query_one("#live-stream-body")
            if "10:11:12" in str(body.render()):
                break
        body = app.query_one("#live-stream-body")
        rendered = str(body.render())
        assert "10:11:12" in rendered, f"expected formatted time; got {rendered!r}"
        assert "tdd_green_complete" in rendered, rendered
        # Raw JSON braces MUST NOT appear for this event
        assert "{\"ts\"" not in rendered and '"state":' not in rendered, (
            f"raw JSON leaked into live stream: {rendered!r}"
        )


@pytest.mark.asyncio
async def test_help_modal_opens_without_crash(tmp_path: Path) -> None:
    """Post-ship bug report: pressing '?' raised
    'HelpModal._render() missing 1 required positional argument: entries'
    because Textual's Widget._render is an internal render-pipeline hook
    and our method overrode it with an incompatible signature. Unit test
    on fuzzy_filter missed this — the modal was never actually mounted."""
    from devboard.tui.help_modal import HelpModal

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
async def test_live_stream_colors_redteam_broken_red(tmp_path: Path) -> None:
    from devboard.tui.anomaly import AnomalyClassifier
    from devboard.tui.live_stream_view import LiveStreamView

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        stream = app.query_one(LiveStreamView)
        clf = AnomalyClassifier()
        result = clf.classify({"event": "redteam_complete", "state": {"verdict": "BROKEN"}})
        assert result is not None
        color, _ = result
        stream.append_line("redteam BROKEN on task t_x", color=color)
        body = app.query_one("#live-stream-body")
        content = str(body.render())
        assert "redteam BROKEN" in content


@pytest.mark.asyncio
async def test_app_wires_tail_worker_to_live_stream(tmp_path: Path) -> None:
    """Red-team round 2 — Attack 1 (CRITICAL): the App must actually drive
    a tail worker that reads .devboard/runs/*.jsonl and pushes classified
    events into LiveStreamView + HealthBar. Unit tests on primitives are
    not enough; the integration must exist in the running App."""
    import json

    _bootstrap_board(tmp_path, ("g_1", "goal-one"))
    runs_dir = tmp_path / ".devboard" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_file = runs_dir / "run_red.jsonl"
    run_file.write_text('{"event": "run_start", "state": {}}\n')

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # Append an anomaly event AFTER the App is running
        run_file.write_text(
            run_file.read_text()
            + json.dumps({"event": "redteam_complete", "state": {"verdict": "BROKEN"}})
            + "\n"
        )
        # Give the worker up to ~2 seconds (20 * 100ms) to notice
        for _ in range(20):
            await pilot.pause(0.1)
            body = app.query_one("#live-stream-body")
            if "BROKEN" in str(body.render()):
                break
        body = app.query_one("#live-stream-body")
        assert "BROKEN" in str(body.render()), (
            "App did not tail the run file and surface the anomaly"
        )


@pytest.mark.asyncio
async def test_live_stream_applies_rich_color_markup_for_anomalies(tmp_path: Path) -> None:
    """Red-team round 3 — Attack 1 (CRITICAL): anomaly lines must be
    rendered with real color spans, not as literal '[red]...[/]' text.
    Textual Content renders `markup=False` as a single plain string with
    zero style spans; `markup=True` produces Span(...) entries with the
    declared style."""
    from devboard.tui.live_stream_view import LiveStreamView

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        stream = app.query_one(LiveStreamView)
        stream.append_line("redteam BROKEN on task t_x", color="red")
        body = app.query_one("#live-stream-body")

        rendered = body.render()
        spans = getattr(rendered, "spans", [])
        # There must be at least one span with "red" styling for the
        # anomaly line — otherwise the user sees literal brackets.
        styles = [str(getattr(s, "style", "")) for s in spans]
        assert any("red" in st for st in styles), (
            f"expected a red style span, got spans={spans}, rendered={rendered!r}"
        )


@pytest.mark.asyncio
async def test_command_line_reopen_clears_stale_error_state(tmp_path: Path) -> None:
    """Red-team round 3 — Attack 2 (HIGH): after an error message, opening
    the command line again must present an empty input; user typing must
    not interleave with the stale error text."""
    _bootstrap_board(tmp_path)
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # Trigger an unknown-command error
        await _run_cmd(pilot, "nope")
        cl = app.query_one("#command-line")
        assert "Unknown" in cl.value  # precondition — we are in error state

        # Re-open command line: value must clear, background must reset
        await pilot.press("colon")
        await pilot.pause()
        assert cl.value == "", f"stale error leaked into reopened input: {cl.value!r}"


@pytest.mark.asyncio
async def test_stale_error_timer_does_not_wipe_new_user_input(tmp_path: Path) -> None:
    """Red-team round 3 — Attack 2b (HIGH): the 1s error-clear timer
    scheduled for a PRIOR error must not wipe the user's subsequently
    typed input."""
    _bootstrap_board(tmp_path)
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # t=0: trigger error, which schedules a 1s timer
        await _run_cmd(pilot, "nope")
        # t=0.3: user reopens and starts typing
        await pilot.press("colon")
        await pilot.pause()
        for ch in "goals":
            await pilot.press(ch)
        cl = app.query_one("#command-line")
        typed = cl.value
        assert typed == "goals", f"precondition — user typed goals, got {typed!r}"
        # t=1.2: wait past the timer
        await pilot.pause(1.1)
        assert cl.value == "goals", (
            f"stale error timer wiped user input: {cl.value!r}"
        )


@pytest.mark.asyncio
async def test_on_input_submitted_catches_arbitrary_handler_exceptions(tmp_path: Path) -> None:
    """Red-team round 2 — Attack 2 (HIGH): any handler exception must be
    displayed as a 1s red hint in the command line, not crash the App."""
    _bootstrap_board(tmp_path)
    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        # Register a handler that raises a generic exception
        app.commands.register(
            "boom", [], lambda: (_ for _ in ()).throw(RuntimeError("nope"))
        )
        await _run_cmd(pilot, "boom")
        # App should still be running and the command-line should still exist
        cl = app.query_one("#command-line")
        assert cl is not None
        assert "nope" in cl.value or cl.styles.background is not None
