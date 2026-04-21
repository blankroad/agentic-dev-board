"""s_009 — overview_render must emit a reasoning fragment per iteration
in the Activity section, and the '계획 요약' step count should use
payload.step_shipping (shipped=True count) not plan.atomic_steps_done."""

from __future__ import annotations


def test_activity_includes_reasoning_fragment_and_accurate_completed_count() -> None:
    from devboard.tui.overview_render import render_overview_body

    payload = {
        "purpose": "fix the dev tab",
        "plan_digest": {
            "locked_hash": "abc",
            "scope_decision": "HOLD",
            "atomic_steps_total": 3,
            # Intentionally 0 here — the renderer must NOT use this value
            # once step_shipping is available.
            "atomic_steps_done": 0,
        },
        "iterations": [
            {
                "iter": 1,
                "phase": "tdd_green",
                "verdict": "GREEN_CONFIRMED",
                "reasoning": "overview TabPane wrapped in VerticalScroll import + CSS added",
                "ts": "2026-04-20T10:00:00+00:00",
                "touched_files": [],
                "diff_stats": {"adds": 0, "dels": 0},
            },
        ],
        "current_state": {"status": "pushed"},
        "step_shipping": [
            {"id": "s_001", "shipped": True},
            {"id": "s_002", "shipped": True},
            {"id": "s_003", "shipped": False},
        ],
    }
    out = render_overview_body(payload)
    # atomic_steps count should reflect step_shipping (2 shipped of 3), not
    # the stale plan_digest.atomic_steps_done=0.
    assert "2 done" in out or "2/3" in out, (
        f"Overview must show completed count from step_shipping (2), not plan_digest; got:\n{out}"
    )
    # Activity section must include a reasoning fragment for iter 1.
    assert "overview TabPane wrapped" in out or "VerticalScroll" in out.lower() or "wrapped" in out, (
        f"Activity section must include a reasoning fragment; got:\n{out}"
    )
