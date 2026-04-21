"""PhaseFlowView — 4-tab TabbedContent that replaces PlanMarkdown +
ActivityTimeline in the TUI center panel.

Data sources:
  Plan tab   — plan_summary.md fallback plan.md fallback empty-state
  Dev tab    — decisions.jsonl rows with phase in dev-phase set
  Result tab — plan.json.atomic_steps checklist + [N/M done] badge
  Review tab — decisions.jsonl rows with phase in review-phase set

Behavioral surface under test:
  * 4 TabPanes in order plan/dev/result/review
  * Plan fallback chain
  * Dev/Review phase filtering
  * Result atomic_steps rendering
  * Number-key 1/2/3/4 activation
  * ctrl+p pin toggle
  * handle_new_decision auto-switch (pin-aware, manual-override-aware)
  * refresh_badges() updates tab labels dynamically
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _mk_goal(
    tmp_path: Path,
    gid: str,
    *,
    plan_md: str | None = None,
    plan_summary_md: str | None = None,
    plan_json: dict | None = None,
) -> None:
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

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
    if plan_md is not None:
        (goal_dir / "plan.md").write_text(plan_md, encoding="utf-8")
    if plan_summary_md is not None:
        (goal_dir / "plan_summary.md").write_text(plan_summary_md, encoding="utf-8")
    if plan_json is not None:
        (goal_dir / "plan.json").write_text(json.dumps(plan_json), encoding="utf-8")


async def _mount(tmp_path: Path, task_id: str | None = None):
    from textual.app import App, ComposeResult
    from textual.binding import Binding

    from devboard.tui.phase_flow import PhaseFlowView
    from devboard.tui.session_derive import SessionContext

    ctx = SessionContext(tmp_path)

    class _Host(App):
        BINDINGS = [
            Binding("ctrl+p", "toggle_phase_flow_pin", "Pin", show=False, priority=True),
        ]

        def compose(self) -> ComposeResult:
            yield PhaseFlowView(ctx, task_id=task_id, id="phase-flow")

        def action_toggle_phase_flow_pin(self) -> None:
            self.query_one(PhaseFlowView).action_toggle_pin()

    return _Host()


@pytest.mark.asyncio
async def test_phase_flow_view_composes_four_tabs_in_order(tmp_path: Path) -> None:
    """s_001: PhaseFlowView composes TabbedContent with 4 TabPanes whose
    ids are 'plan', 'dev', 'result', 'review' in that order.

    # guards: integration-wiring, compose-once-staleness
    """
    _mk_goal(tmp_path, "g1", plan_md="# P\n")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent, TabPane

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        panes = list(tc.query(TabPane))
        pane_ids = [p.id for p in panes]
        assert pane_ids == ["overview", "plan", "dev", "result", "review"], (
            f"expected ordered [overview,plan,dev,result,review], got {pane_ids}"
        )


@pytest.mark.asyncio
async def test_plan_tab_renders_plan_summary_md(tmp_path: Path) -> None:
    """s_002: Plan tab body contains text from plan_summary.md when that
    file exists for the active goal.

    # guards: binary-file-read-tolerance, integration-wiring
    """
    marker = "PLAN_SUMMARY_MARKER_XYZ"
    _mk_goal(
        tmp_path,
        "g1",
        plan_summary_md=f"# Summary\n\n{marker}\n",
        plan_md="# raw\nRAW_PLAN_MARKER\n",
    )
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()

        flow = app.query_one("#phase-flow")
        body = flow.plan_body_text()
        assert marker in body, (
            f"Plan tab body should include plan_summary.md marker {marker!r}; got: {body[:300]!r}"
        )


@pytest.mark.asyncio
async def test_plan_tab_falls_back_to_plan_md_when_no_summary(tmp_path: Path) -> None:
    """s_003: Plan tab body falls back to plan.md content when
    plan_summary.md is absent.

    # guards: binary-file-read-tolerance
    """
    marker = "RAW_PLAN_MARKER_ABC"
    _mk_goal(tmp_path, "g1", plan_md=f"# raw\n{marker}\n")  # no summary
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").plan_body_text()
        assert marker in body, (
            f"Plan tab should fall back to plan.md and include {marker!r}; got: {body[:300]!r}"
        )


def _write_decisions(
    tmp_path: Path, gid: str, task_id: str, rows: list[dict]
) -> None:
    tdir = tmp_path / ".devboard" / "goals" / gid / "tasks" / task_id
    tdir.mkdir(parents=True, exist_ok=True)
    with (tdir / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


@pytest.mark.asyncio
async def test_dev_tab_lists_rows_with_dev_phases(tmp_path: Path) -> None:
    """s_005: Dev tab body contains rows whose phase ∈
    {dev, tdd, eng_review, iron_law, rca}.

    v2.3 (g_20260420_231710_1acaa6, borderline B): card format must also
    produce label markers (behavior:/reasoning:/test:/impl:) and a card
    divider so the structural contract is explicit, not inferred.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    _write_decisions(
        tmp_path,
        "g1",
        "t1",
        [
            {"iter": 7, "phase": "tdd_green", "verdict_source": "GREEN_MARKER_7",
             "reasoning": "s_007 impl done"},
            {"iter": 6, "phase": "eng_review", "verdict_source": "ENG_MARKER_6",
             "reasoning": "eng review notes"},
            {"iter": 5, "phase": "reviewer", "verdict_source": "SHOULD_NOT_APPEAR"},
        ],
    )
    app = await _mount(tmp_path, task_id="t1")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow")
        body = flow.dev_body_text()
        assert "GREEN_MARKER_7" in body, (
            f"Dev tab should include tdd_green row; got: {body[:300]!r}"
        )
        assert "ENG_MARKER_6" in body, (
            f"Dev tab should include eng_review row; got: {body[:300]!r}"
        )
        # Structure assertions — card format guard.
        assert "reasoning:" in body, (
            f"Dev tab must emit `reasoning:` label in card format; got: {body[:400]!r}"
        )
        assert "─────" in body, (
            f"Dev tab must emit card divider (5+ ─) between iter cards; got: {body[:400]!r}"
        )


@pytest.mark.asyncio
async def test_dev_tab_excludes_review_phases(tmp_path: Path) -> None:
    """s_006: Dev tab body excludes rows whose phase ∈ review-phase set
    {reviewer, cso, redteam, parallel_review}.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    _write_decisions(
        tmp_path,
        "g1",
        "t1",
        [
            {"iter": 9, "phase": "reviewer", "verdict_source": "REVIEWER_LEAK"},
            {"iter": 8, "phase": "cso", "verdict_source": "CSO_LEAK"},
            {"iter": 7, "phase": "redteam", "verdict_source": "REDTEAM_LEAK"},
            {"iter": 6, "phase": "parallel_review", "verdict_source": "PARALLEL_LEAK"},
        ],
    )
    app = await _mount(tmp_path, task_id="t1")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").dev_body_text()
        for leaked in ("REVIEWER_LEAK", "CSO_LEAK", "REDTEAM_LEAK", "PARALLEL_LEAK"):
            assert leaked not in body, (
                f"Dev tab must NOT include review-phase marker {leaked!r}; got: {body[:300]!r}"
            )


@pytest.mark.asyncio
async def test_result_tab_renders_atomic_steps_checklist(tmp_path: Path) -> None:
    """s_007: Result tab body renders one line per atomic_step from
    plan.json with '[x]' for completed=true and '[ ]' otherwise.
    """
    _mk_goal(
        tmp_path,
        "g1",
        plan_md="# P",
        plan_json={
            "atomic_steps": [
                {"id": "s_001", "behavior": "STEP_ONE_BEHAVIOR", "completed": True},
                {"id": "s_002", "behavior": "STEP_TWO_BEHAVIOR", "completed": False},
            ],
        },
    )
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").result_body_text()
        assert "[x]" in body and "STEP_ONE_BEHAVIOR" in body, (
            f"Result tab should show completed s_001 with [x] marker; got: {body[:400]!r}"
        )
        assert "[ ]" in body and "STEP_TWO_BEHAVIOR" in body, (
            f"Result tab should show pending s_002 with [ ] marker; got: {body[:400]!r}"
        )


@pytest.mark.asyncio
async def test_result_tab_shows_progress_badge(tmp_path: Path) -> None:
    """s_008: Result tab body includes a '[N/M done]' progress badge."""
    _mk_goal(
        tmp_path,
        "g1",
        plan_md="# P",
        plan_json={
            "atomic_steps": [
                {"id": "s_001", "behavior": "a", "completed": True},
                {"id": "s_002", "behavior": "b", "completed": True},
                {"id": "s_003", "behavior": "c", "completed": False},
                {"id": "s_004", "behavior": "d", "completed": False},
                {"id": "s_005", "behavior": "e", "completed": False},
            ],
        },
    )
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").result_body_text()
        assert "[2/5 done]" in body, (
            f"Result tab should include progress badge '[2/5 done]'; got: {body[:400]!r}"
        )


@pytest.mark.asyncio
async def test_review_tab_lists_only_review_phases(tmp_path: Path) -> None:
    """s_009: Review tab body contains only rows whose phase ∈
    {reviewer, cso, redteam, parallel_review, approval}.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    _write_decisions(
        tmp_path,
        "g1",
        "t1",
        [
            {"iter": 10, "phase": "review", "verdict_source": "REVIEW_OK"},
            {"iter": 9, "phase": "cso", "verdict_source": "CSO_OK"},
            {"iter": 8, "phase": "redteam", "verdict_source": "REDTEAM_OK"},
            {"iter": 7, "phase": "parallel_review", "verdict_source": "PARALLEL_OK"},
            {"iter": 6, "phase": "approval", "verdict_source": "APPROVAL_OK"},
            {"iter": 5, "phase": "tdd_green", "verdict_source": "DEV_LEAK"},
            {"iter": 4, "phase": "eng_review", "verdict_source": "ENG_LEAK"},
        ],
    )
    app = await _mount(tmp_path, task_id="t1")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").review_body_text()
        for expected in (
            "REVIEW_OK",
            "CSO_OK",
            "REDTEAM_OK",
            "PARALLEL_OK",
            "APPROVAL_OK",
        ):
            assert expected in body, (
                f"Review tab should include {expected!r}; got: {body[:400]!r}"
            )
        for leaked in ("DEV_LEAK", "ENG_LEAK"):
            assert leaked not in body, (
                f"Review tab must NOT include non-review marker {leaked!r}; got: {body[:400]!r}"
            )


@pytest.mark.asyncio
async def test_number_key_three_activates_dev_tab(tmp_path: Path) -> None:
    """s_010 (v3): With 5-tab overview-first layout, key '3' activates Dev."""
    _mk_goal(tmp_path, "g1", plan_md="# P")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        assert tc.active == "overview", (
            f"initial active expected 'overview', got {tc.active!r}"
        )

        await pilot.press("3")
        await pilot.pause()
        assert tc.active == "dev", (
            f"pressing '3' must activate Dev tab; active={tc.active!r}"
        )


@pytest.mark.asyncio
async def test_ctrl_p_toggles_pinned_reactive(tmp_path: Path) -> None:
    """s_011: Pressing ctrl+p toggles PhaseFlowView.pinned from False → True."""
    _mk_goal(tmp_path, "g1", plan_md="# P")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow")
        assert flow.pinned is False, f"pinned must default to False, got {flow.pinned!r}"

        await pilot.press("ctrl+p")
        await pilot.pause()
        assert flow.pinned is True, (
            f"ctrl+p must flip pinned to True; got {flow.pinned!r}"
        )


@pytest.mark.asyncio
async def test_handle_new_decision_reviewer_activates_review_tab(
    tmp_path: Path,
) -> None:
    """s_012: handle_new_decision with phase='reviewer' on pin=False
    activates the Review tab.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        assert flow.pinned is False
        assert tc.active == "overview"

        flow.handle_new_decision({"iter": 99, "phase": "review"})
        await pilot.pause()
        assert tc.active == "review", (
            f"handle_new_decision(reviewer) must activate Review tab; active={tc.active!r}"
        )


@pytest.mark.asyncio
async def test_handle_new_decision_blocked_when_pinned(tmp_path: Path) -> None:
    """s_013: handle_new_decision with phase='reviewer' on pin=True leaves
    TabbedContent.active unchanged.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        # Pin the view BEFORE the decision arrives.
        flow.pinned = True
        assert tc.active == "overview"

        flow.handle_new_decision({"iter": 99, "phase": "review"})
        await pilot.pause()
        assert tc.active == "overview", (
            f"pin=True must block auto-switch; active={tc.active!r}"
        )


@pytest.mark.asyncio
async def test_manual_switch_blocks_auto_switch_for_ten_seconds(
    tmp_path: Path,
) -> None:
    """s_014: Manual tab switch via number key sets manual_override_until
    to now+10s; handle_new_decision within that window is skipped.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        assert flow.pinned is False

        # Manual switch to Plan via key '2' (overview is now key '1');
        # either way the press establishes the override window.
        await pilot.press("2")
        await pilot.pause()
        assert tc.active == "plan"

        # Window begin must be in the near future (>= now, <= now + 10.5).
        import time

        now = time.monotonic()
        until = flow.manual_override_until
        assert until is not None, "manual_override_until should be set after manual press"
        assert now <= until <= now + 10.5, (
            f"override window must be ≈10s from now; now={now} until={until}"
        )

        # An auto-switch attempt within the window must be skipped.
        flow.handle_new_decision({"iter": 42, "phase": "reviewer"})
        await pilot.pause()
        assert tc.active == "plan", (
            f"handle_new_decision within manual-override window must be skipped; "
            f"user switched to plan via key '2', so stays at plan; "
            f"active={tc.active!r}"
        )


@pytest.mark.asyncio
async def test_dev_badge_shows_count_over_total(tmp_path: Path) -> None:
    """s_015: refresh_badges() updates Dev tab label (or body header) to
    'Dev N/M' where N = dev-phase decisions count and M = atomic_steps
    total.
    """
    _mk_goal(
        tmp_path,
        "g1",
        plan_md="# P",
        plan_json={
            "atomic_steps": [
                {"id": f"s_{i:03d}", "behavior": "x", "completed": False}
                for i in range(1, 21)  # total = 20
            ],
        },
    )
    _write_decisions(
        tmp_path,
        "g1",
        "t1",
        [
            {"iter": 3, "phase": "tdd_green", "verdict_source": "G3"},
            {"iter": 2, "phase": "tdd_green", "verdict_source": "G2"},
            {"iter": 1, "phase": "tdd_green", "verdict_source": "G1"},
            {"iter": 0, "phase": "reviewer", "verdict_source": "R0"},
        ],
    )
    app = await _mount(tmp_path, task_id="t1")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow")
        flow.refresh_badges()
        await pilot.pause()
        dev_badge = flow.dev_badge_text()
        # 3 dev decisions over 20 atomic_steps → "Dev 3/20"
        assert "3/20" in dev_badge, (
            f"Dev badge should read 'Dev 3/20'; got: {dev_badge!r}"
        )


@pytest.mark.asyncio
async def test_app_center_col_mounts_phase_flow_view(tmp_path: Path) -> None:
    """s_016: DevBoardApp.compose yields a PhaseFlowView with id='phase-flow'
    inside center-col, replacing the legacy PlanMarkdown + ActivityTimeline
    pair.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    from devboard.tui.app import DevBoardApp
    from devboard.tui.phase_flow import PhaseFlowView

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow", PhaseFlowView)
        assert flow is not None
        # Legacy widgets must no longer be mounted by app.compose.
        assert not app.query("#plan-markdown"), (
            "app.compose must no longer mount PlanMarkdown (#plan-markdown)"
        )
        assert not app.query("#activity-timeline"), (
            "app.compose must no longer mount ActivityTimeline (#activity-timeline)"
        )


@pytest.mark.asyncio
async def test_app_on_stream_event_delegates_to_phase_flow_handle_tick(
    tmp_path: Path,
) -> None:
    """s_017: DevBoardApp.on_stream_event invokes
    phase_flow_view.handle_tick() at least once per event.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    from devboard.tui.app import DevBoardApp
    from devboard.tui.phase_flow import PhaseFlowView

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow", PhaseFlowView)

        calls: list[None] = []
        orig = flow.handle_tick

        def _spy() -> None:  # noqa: ANN202
            calls.append(None)
            return orig()

        flow.handle_tick = _spy  # type: ignore[method-assign]
        app.on_stream_event("some event text", None)
        await pilot.pause()
        assert len(calls) >= 1, (
            f"on_stream_event should delegate to phase_flow.handle_tick; calls={len(calls)}"
        )


@pytest.mark.asyncio
async def test_app_refresh_for_active_goal_reloads_phase_flow(
    tmp_path: Path,
) -> None:
    """s_018: DevBoardApp.refresh_for_active_goal calls
    phase_flow_view.refresh_content().
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    from devboard.tui.app import DevBoardApp
    from devboard.tui.phase_flow import PhaseFlowView

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow", PhaseFlowView)

        calls: list[None] = []
        orig = flow.refresh_content

        def _spy(*args, **kwargs) -> None:  # noqa: ANN001,ANN002,ANN003
            calls.append(None)
            return orig(*args, **kwargs)

        flow.refresh_content = _spy  # type: ignore[method-assign]
        app.refresh_for_active_goal()
        await pilot.pause()
        assert len(calls) >= 1, (
            f"refresh_for_active_goal should invoke phase_flow.refresh_content; calls={len(calls)}"
        )


@pytest.mark.asyncio
async def test_review_tab_accepts_canonical_review_phase(tmp_path: Path) -> None:
    """s_021 CRITICAL: the canonical phase string in decisions.jsonl is
    'review' (see orchestrator/graph.py:332, analytics/retro.py:92,
    kanban.py:63, docgen.py:126/176, metrics.py:149, narrative/generator.py:84,
    cli.py:828) — NOT 'reviewer'. Review tab + PHASE_TO_TAB both must key
    on 'review' or the feature is silently broken in production.

    # guards: phase-name-canon-match
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    _write_decisions(
        tmp_path,
        "g1",
        "t1",
        [
            {"iter": 5, "phase": "review", "verdict_source": "CANONICAL_REVIEW_MARK"},
        ],
    )
    app = await _mount(tmp_path, task_id="t1")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        flow = app.query_one("#phase-flow")

        # (a) body filter: 'review' row must appear in Review tab body.
        body = flow.review_body_text()
        assert "CANONICAL_REVIEW_MARK" in body, (
            f"Review tab must surface phase='review' rows (canonical); got: {body[:300]!r}"
        )

        # (b) auto-switch: handle_new_decision(phase='review') must route
        # to Review tab.
        from textual.widgets import TabbedContent

        tc = flow.query_one(TabbedContent)
        assert tc.active == "overview"
        flow.handle_new_decision({"iter": 5, "phase": "review"})
        await pilot.pause()
        assert tc.active == "review", (
            f"handle_new_decision(phase='review') must route to Review tab; "
            f"active={tc.active!r}"
        )


@pytest.mark.asyncio
async def test_number_keys_work_in_real_devboard_app(tmp_path: Path) -> None:
    """s_022 CRITICAL: when the real DevBoardApp boots, initial focus goes
    to the sidebar ListView (#resources-goals, see app.py:154). Widget-
    level BINDINGS with priority=True on PhaseFlowView then fail to fire
    for character keys like '2' — repro verified at red-team round 1.

    Fix: promote 1/2/3/4 to DevBoardApp.BINDINGS (same pattern as
    ctrl+p) so they survive any focus chain.

    # guards: widget-binding-focus-chain
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    from devboard.tui.app import DevBoardApp
    from textual.widgets import TabbedContent

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        tc = app.query_one("#phase-flow").query_one(TabbedContent)
        assert tc.active == "overview", (
            f"precondition: initial active=overview; got {tc.active!r}"
        )
        # Do NOT call .focus() — we must exercise the real default focus
        # chain (ListView #resources-goals).
        await pilot.press("3")
        await pilot.pause()
        assert tc.active == "dev", (
            f"press('3') in real DevBoardApp must switch to Dev tab regardless "
            f"of sidebar focus; active={tc.active!r}"
        )


@pytest.mark.asyncio
async def test_gauntlet_phases_route_to_plan_tab(tmp_path: Path) -> None:
    """s_023 HIGH: during live planning the 5-step Gauntlet emits
    phases 'frame' / 'scope' / 'arch' / 'challenge' / 'decide'. These
    should auto-activate the Plan tab so the user sees planning progress.
    Red-team round 1 flagged silent 'stay on whatever' behavior.
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        # Jump to Review first so we can detect the switch-back to Plan.
        tc.active = "review"
        await pilot.pause()
        assert tc.active == "review"

        flow.handle_new_decision({"iter": 1, "phase": "arch"})
        await pilot.pause()
        assert tc.active == "plan", (
            f"gauntlet 'arch' phase must route to Plan tab; active={tc.active!r}"
        )


@pytest.mark.asyncio
async def test_handle_tick_dispatches_newly_appended_row_not_max_iter(
    tmp_path: Path,
) -> None:
    """s_024 HIGH: handle_tick must dispatch the row most recently
    appended to decisions.jsonl — not the max-iter row. During
    agentboard-replay the new run re-enters an older checkpoint, so the
    appended iter can be LOWER than existing iters. decisions_for_task
    sorts by iter DESC and rows[0] was the stale max-iter row.

    Repro: pre-write [iter=10 phase='review']; append [iter=3 phase='tdd_red'].
    Expected: Dev tab activates (not Review).

    # guards: replay-iter-order
    """
    _mk_goal(tmp_path, "g1", plan_md="# P")
    # Initial decision: iter=10 review.
    _write_decisions(
        tmp_path,
        "g1",
        "t1",
        [
            {"iter": 10, "phase": "review", "verdict_source": "OLD_REVIEW"},
        ],
    )
    app = await _mount(tmp_path, task_id="t1")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        assert tc.active == "overview"

        # Append a LOWER-iter dev row, as agentboard-replay would.
        decisions_path = (
            tmp_path
            / ".devboard"
            / "goals"
            / "g1"
            / "tasks"
            / "t1"
            / "decisions.jsonl"
        )
        with decisions_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"iter": 3, "phase": "tdd_red"}) + "\n")

        flow.handle_tick()
        await pilot.pause()
        assert tc.active == "dev", (
            f"handle_tick must dispatch the newly-appended row (iter=3 tdd_red), "
            f"not rows[0] (iter=10 review); active={tc.active!r}"
        )


def test_help_modal_documents_phase_flow_keys() -> None:
    """s_019: HelpModal default entries include references to both '1/2/3/4'
    (tab jump) and 'ctrl+p' (pin) so the user can discover phase-flow
    controls.
    """
    from devboard.tui.help_modal import DEFAULT_ENTRIES

    haystack = " ".join(e.haystack for e in DEFAULT_ENTRIES).lower()
    assert "1/2/3/4" in haystack or ("1" in haystack and "2" in haystack and "3" in haystack and "4" in haystack and "tab" in haystack), (
        f"HelpModal should document '1/2/3/4' tab-jump keys; got entries:\n{haystack[:500]!r}"
    )
    assert "ctrl+p" in haystack, (
        f"HelpModal should document 'ctrl+p' pin; got entries:\n{haystack[:500]!r}"
    )


@pytest.mark.asyncio
async def test_plan_tab_empty_state_when_no_plan_files(tmp_path: Path) -> None:
    """s_004: Plan tab body shows 'Plan not locked' empty-state when
    neither plan_summary.md nor plan.md exists for the active goal.
    """
    # Goal dir exists (active) but no plan files inside.
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    try:
        board = store.load_board()
    except Exception:
        board = BoardState()
    board.goals.append(Goal(id="g_empty", title="g_empty", status=GoalStatus.active))
    store.save_board(board)
    (tmp_path / ".devboard" / "goals" / "g_empty").mkdir(parents=True, exist_ok=True)

    app = await _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").plan_body_text()
        assert "Plan not locked" in body, (
            f"Plan tab should show empty-state 'Plan not locked' when no plan files; got: {body[:300]!r}"
        )
