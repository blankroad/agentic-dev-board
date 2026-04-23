"""PhaseFlowView v3 — 5-tab with Overview anchor (s_012, s_013)."""

from __future__ import annotations

from pathlib import Path

import pytest


def _mk_goal(tmp_path: Path, gid: str = "g1", plan_md: str = "# P\n") -> None:
    d = tmp_path / ".agentboard" / "goals" / gid
    d.mkdir(parents=True)
    (d / "plan.md").write_text(plan_md, encoding="utf-8")


def _mount(tmp_path: Path):
    from textual.app import App, ComposeResult
    from agentboard.tui.phase_flow import PhaseFlowView
    from agentboard.tui.session_derive import SessionContext

    class _Host(App[None]):
        def compose(self) -> ComposeResult:
            ctx = SessionContext(tmp_path)
            yield PhaseFlowView(ctx, task_id=None, id="phase-flow")

    return _Host()


@pytest.mark.asyncio
async def test_phase_flow_five_tabs_overview_initial(tmp_path: Path) -> None:
    """s_012: 5 tabs [overview, plan, dev, result, review]; overview is initial."""
    _mk_goal(tmp_path)
    app = _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent, TabPane

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        panes = list(tc.query(TabPane))
        assert [p.id for p in panes] == ["overview", "plan", "dev", "result", "review"]
        assert tc.active == "overview"


@pytest.mark.asyncio
async def test_phase_flow_keybinding_1_overview(tmp_path: Path) -> None:
    """s_013: key '1' activates overview tab (was 'plan')."""
    _mk_goal(tmp_path)
    app = _mount(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        flow = app.query_one("#phase-flow")
        tc = flow.query_one(TabbedContent)
        # start at overview, switch elsewhere, then press 1
        tc.active = "dev"
        await pilot.pause()
        flow.focus()
        await pilot.press("1")
        await pilot.pause()
        assert tc.active == "overview"


# ---- redteam blocker reproductions (iter 16) ----------------------------------


@pytest.mark.asyncio
async def test_dev_body_uses_render_dev_timeline(tmp_path: Path) -> None:
    """HIGH-Missing: _load_dev_body must call render_dev_timeline.

    # guards: dead-renderer wiring
    """
    _mk_goal(tmp_path)
    # write a dev iter so the renderer produces its characteristic "delta :" block
    gdir = tmp_path / ".agentboard" / "goals" / "g1" / "tasks" / "t1"
    (gdir / "changes").mkdir(parents=True)
    (gdir / "decisions.jsonl").write_text(
        '{"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_MARKER", "ts": "t1"}\n',
        encoding="utf-8",
    )
    (gdir / "changes" / "iter_1.diff").write_text(
        "+++ b/x.py\n+a\n+b\n", encoding="utf-8"
    )

    from textual.app import App, ComposeResult
    from agentboard.tui.phase_flow import PhaseFlowView
    from agentboard.tui.session_derive import SessionContext

    class _Host(App[None]):
        def compose(self) -> ComposeResult:
            yield PhaseFlowView(SessionContext(tmp_path), task_id="t1", id="phase-flow")

    app = _Host()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").dev_body_text()
        # render_dev_timeline outputs either "## Scope baseline" (As-Is→To-Be,
        # when git-based code_delta populates) or "iter N · phase" (fallback).
        # Both are exclusive to the new renderer — not the legacy inline loop.
        # v2.3 card format: header is `iter N · step_id · phase · verdict`
        # (step_id sits between iter and phase). Accept either rollup header
        # or the card-format header.
        assert (
            "## Scope baseline" in body
            or "## Iterations" in body
            or "iter 1 · " in body and "tdd_green" in body
        ), (
            f"Dev tab must use render_dev_timeline; got: {body[:400]!r}"
        )


@pytest.mark.asyncio
async def test_review_body_uses_render_review_sections(tmp_path: Path) -> None:
    """HIGH-Missing: _load_review_body must call render_review_sections."""
    _mk_goal(tmp_path)
    from textual.app import App, ComposeResult
    from agentboard.tui.phase_flow import PhaseFlowView
    from agentboard.tui.session_derive import SessionContext

    class _Host(App[None]):
        def compose(self) -> ComposeResult:
            yield PhaseFlowView(SessionContext(tmp_path), task_id=None, id="phase-flow")

    app = _Host()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#phase-flow").review_body_text()
        assert "Improved" in body and "ToImprove" in body, (
            f"Review tab must use render_review_sections (4 text labels); got: {body[:400]!r}"
        )


def test_plan_digest_rejects_truthy_string_completed(tmp_path: Path) -> None:
    """HIGH-Type: completed='false' (string) must NOT inflate done count.

    # guards: truthy-string boolean coercion
    """
    from agentboard.analytics.overview_payload import build_overview_payload

    gdir = tmp_path / ".agentboard" / "goals" / "g1"
    gdir.mkdir(parents=True)
    (gdir / "plan.json").write_text(
        '{"atomic_steps": ['
        '{"id": "s1", "completed": "false"},'
        '{"id": "s2", "completed": "true"},'
        '{"id": "s3", "completed": true},'
        '{"id": "s4", "completed": 0}'
        ']}',
        encoding="utf-8",
    )
    out = build_overview_payload(tmp_path, "g1", task_id=None)
    # only the actual boolean True counts
    assert out["plan_digest"]["atomic_steps_done"] == 1
    assert out["plan_digest"]["atomic_steps_total"] == 4
