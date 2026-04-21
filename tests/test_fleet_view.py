"""FleetView stub widget test (f_005)."""
from __future__ import annotations


def test_fleet_view_renders_rows_from_summaries() -> None:
    """f_005: FleetView stub renders one row per GoalSummary with sparkline."""
    from agentboard.models import GoalSummary
    from agentboard.tui.fleet_view import FleetView, render_fleet_rows

    summaries = [
        GoalSummary(
            gid="g_a", title="Alpha", iter_count=3,
            last_phase="tdd_green", last_verdict="GREEN",
            sparkline_phases=["tdd_red", "tdd_green", "tdd_green"],
            updated_at_iso="2026-04-22T00:00:00+00:00",
        ),
        GoalSummary(
            gid="g_b", title="Beta", iter_count=7,
            last_phase="review", last_verdict="SURVIVED",
            sparkline_phases=["tdd_green", "redteam"],
            updated_at_iso="2026-04-22T00:00:00+00:00",
        ),
    ]

    output = render_fleet_rows(summaries)
    assert "g_a" in output
    assert "Alpha" in output
    assert "g_b" in output
    assert "Beta" in output
    assert "3" in output  # iter count
    assert "7" in output
    assert "▇" in output  # sparkline glyph

    # Widget instantiates + accepts summaries
    view = FleetView(summaries=summaries)
    assert view._summaries == summaries
