"""Tests for render_result_timeline (s_010)."""

from agentboard.tui.result_timeline_render import render_result_timeline


def test_render_result_timeline_checklist_with_ts() -> None:
    payload = {
        "plan_digest": {
            "atomic_steps_total": 3,
            "atomic_steps_done": 2,
            "atomic_steps": [
                {"id": "s_001", "behavior": "parse_numstat regular", "completed": True},
                {"id": "s_002", "behavior": "parse_numstat binary", "completed": True},
                {"id": "s_003", "behavior": "build payload no task", "completed": False},
            ],
        },
        "iterations": [
            {"iter": 1, "phase": "tdd_green", "verdict": "GREEN_CONFIRMED",
             "ts": "2026-04-20T13:30:00"},
            {"iter": 2, "phase": "tdd_green", "verdict": "GREEN_CONFIRMED",
             "ts": "2026-04-20T13:38:00"},
        ],
    }
    out = render_result_timeline(payload)
    assert "2/3" in out
    assert "[x] s_001" in out
    assert "[x] s_002" in out
    assert "[ ] s_003" in out
    # timestamps of completed green iters appear
    assert "2026-04-20T13:30:00" in out
    assert "2026-04-20T13:38:00" in out


def test_render_result_timeline_empty() -> None:
    assert "Plan not locked" in render_result_timeline({})
