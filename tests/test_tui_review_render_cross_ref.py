"""s_011 — review_sections_render must source Improved/ToImprove/Learned
from payload.risk_delta + payload.learnings, rendering whatever Phase A's
overview_payload produced."""

from __future__ import annotations


def test_review_sections_source_from_payload_fields() -> None:
    from devboard.tui.review_sections_render import render_review_sections

    payload = {
        "risk_delta": {
            "resolved": ["CRITICAL: overview_payload data pipeline"],
            "remaining": ["HIGH: Plan synthesis still shallow"],
            "followups": ["Expand Plan synthesis to LLM-backed"],
        },
        "learnings": [
            # Note: new _load_learnings_from_files emits `summary` (not
            # `content`). Renderer must tolerate either key.
            {
                "name": "pilot-test-must-not-mask-default-focus-bug",
                "summary": "Never call widget.focus() in Pilot tests before keyboard input",
                "tags": ["tui"],
                "category": "pattern",
                "confidence": 0.7,
            },
        ],
    }
    out = render_review_sections(payload)
    assert "CRITICAL: overview_payload" in out, (
        f"Improved must source from risk_delta.resolved:\n{out}"
    )
    assert "HIGH: Plan synthesis" in out, (
        f"ToImprove must source from risk_delta.remaining:\n{out}"
    )
    assert "pilot-test-must-not-mask-default-focus-bug" in out, (
        f"Learned must source from payload.learnings:\n{out}"
    )
    # Learning summary must surface in output, not appear as "(no content)".
    assert "Never call widget.focus()" in out or "Pilot tests" in out, (
        f"Learning summary/content must appear in output:\n{out}"
    )
