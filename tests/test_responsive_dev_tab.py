"""Responsive layout breakpoint tests (M1b m_008)."""
from __future__ import annotations


def test_responsive_layout_breakpoints() -> None:
    from agentboard.tui.responsive import responsive_layout

    # 3-pane: ≥120
    assert responsive_layout(120) == "3pane"
    assert responsive_layout(200) == "3pane"
    # 2-pane: 100-119
    assert responsive_layout(119) == "2pane"
    assert responsive_layout(100) == "2pane"
    # 1-pane: 80-99
    assert responsive_layout(99) == "1pane"
    assert responsive_layout(80) == "1pane"
    # banner: <80
    assert responsive_layout(79) == "banner"
    assert responsive_layout(40) == "banner"
    assert responsive_layout(0) == "banner"
