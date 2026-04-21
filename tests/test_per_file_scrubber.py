"""PerFileScrubber widget tests (M1b m_005, m_006, m_007)."""
from __future__ import annotations


def test_per_file_scrubber_renders_sparkline() -> None:
    """m_005: PerFileScrubber renders a sparkline string with one cell per
    phase marker, using tui_tokens phase colors.
    """
    from agentboard.tui.per_file_scrubber import PerFileScrubber, render_sparkline

    text = render_sparkline(["tdd_red", "tdd_green", "redteam"])
    # 3 input markers → 3 cells (each ▇ glyph)
    # Verify glyph appears 3 times (block character)
    assert text.count("▇") == 3


def test_per_file_scrubber_segment_aggregation_over_30() -> None:
    """m_006: PerFileScrubber aggregates to ≤30 cells when len > 30."""
    from agentboard.tui.per_file_scrubber import render_sparkline

    long_input = ["tdd_green"] * 50
    text = render_sparkline(long_input)
    cells = text.count("▇")
    assert cells <= 30, f"expected aggregation to ≤30 cells, got {cells}"
    assert cells >= 25, f"expected meaningful density, got {cells}"  # not collapsed to nothing


def test_per_file_scrubber_click_dispatches_message() -> None:
    """m_007: PerFileScrubber.handle_segment_click(x) computes segment index
    and returns the iter_n that segment maps to.

    Pure logic test — Pilot integration covered by m_016 e2e.
    """
    from agentboard.tui.per_file_scrubber import segment_index_for_x

    # 10 markers in 30 cell width: each cell ~3 chars
    # x=5 (in cell 1-2 zone) → segment 1
    # x=27 (in cell 9 zone) → segment 9
    assert segment_index_for_x(x=0, total_cells=10, width=10) == 0
    assert segment_index_for_x(x=5, total_cells=10, width=10) == 5
    assert segment_index_for_x(x=9, total_cells=10, width=10) == 9
    # x beyond width → clamped to last
    assert segment_index_for_x(x=100, total_cells=10, width=10) == 9
    # negative → clamped to 0
    assert segment_index_for_x(x=-5, total_cells=10, width=10) == 0
