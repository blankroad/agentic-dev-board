"""Tests for render_review_sections (s_011)."""

from agentboard.tui.review_sections_render import render_review_sections


def test_render_review_sections_four_text_headers() -> None:
    payload = {
        "plan_digest": {
            "atomic_steps": [
                {"id": "s_001", "behavior": "parse numstat", "completed": True},
                {"id": "s_002", "behavior": "build payload", "completed": False},
            ],
        },
        "learnings": [
            {"name": "tui-keybinding-shift-breaks-snapshot", "content": "Shift 1..4→1..5 breaks fixtures", "confidence": 0.8},
        ],
        "followups": [
            "R5 우측 패널 재설계 — 후속 goal candidate",
            "PM demo + 피드백 수집",
        ],
    }
    md = render_review_sections(payload)
    # text labels only (no emoji) per borderline decision
    assert "Improved" in md
    assert "ToImprove" in md
    assert "Learned" in md
    assert "TODOs" in md
    assert "parse numstat" in md  # completed → improved
    assert "build payload" in md  # not completed → to-improve
    assert "tui-keybinding-shift-breaks-snapshot" in md
    assert "R5" in md
