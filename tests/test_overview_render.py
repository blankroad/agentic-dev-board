"""Tests for render_overview_body (s_008)."""

from agentboard.tui.overview_render import render_overview_body


def test_render_overview_body_four_sections() -> None:
    payload = {
        "purpose": "Center panel redesign",
        "plan_digest": {
            "locked_hash": "c6c78fbd34479f61",
            "scope_decision": "SELECTIVE",
            "atomic_steps_total": 15,
            "atomic_steps_done": 7,
        },
        "iterations": [
            {"iter": 1, "phase": "tdd_red", "verdict": "RED_CONFIRMED",
             "touched_files": ["a.py"], "diff_stats": {"adds": 10, "dels": 0}, "ts": "t1"},
        ],
        "current_state": {"status": "in_progress", "last_iter": 1},
        "learnings": [],
        "followups": [],
    }
    md = render_overview_body(payload)
    assert "목적" in md
    assert "계획 요약" in md
    assert "활동" in md
    assert "현재 상태" in md
    assert "Center panel redesign" in md
    assert "c6c78fbd34479f61" in md
