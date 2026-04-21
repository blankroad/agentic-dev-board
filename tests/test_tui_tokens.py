"""Design Tokens module exports (M1b m_001)."""
from __future__ import annotations


def test_tui_tokens_exports_required_constants() -> None:
    from agentboard.tui import tui_tokens as t

    # Verdict colors (3)
    assert t.VERDICT_COLOR_OK.startswith("#") and len(t.VERDICT_COLOR_OK) == 7
    assert t.VERDICT_COLOR_FAIL.startswith("#") and len(t.VERDICT_COLOR_FAIL) == 7
    assert t.VERDICT_COLOR_PENDING.startswith("#") and len(t.VERDICT_COLOR_PENDING) == 7

    # Phase colors (5)
    for name in ("PHASE_COLOR_PLAN", "PHASE_COLOR_TDD", "PHASE_COLOR_REVIEW",
                 "PHASE_COLOR_APPROVAL", "PHASE_COLOR_RCA"):
        val = getattr(t, name)
        assert isinstance(val, str) and val.startswith("#") and len(val) == 7

    # Spacing (3)
    assert t.SPACING_S == 4
    assert t.SPACING_M == 8
    assert t.SPACING_L == 12

    # Motion + focus
    assert t.MOTION_DRAWER_MS == 150
    assert isinstance(t.FOCUS_INDICATOR_STYLE, str)

    # Responsive breakpoints
    assert t.BREAKPOINT_3PANE == 120
    assert t.BREAKPOINT_2PANE == 100
    assert t.BREAKPOINT_1PANE == 80
