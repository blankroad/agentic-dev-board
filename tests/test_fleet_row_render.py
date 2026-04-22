"""Pure-fn render helpers for FleetScreen rows (M2-fleet-tui s_001)."""
from __future__ import annotations


def test_render_fleet_row_cells_selection_and_cap() -> None:
    """s_001: render_fleet_row_cells emits Rich Text with ▶ on selected + heat cells capped at 8."""
    from agentboard.models import GoalSummary
    from agentboard.tui.fleet_row_render import render_fleet_row_cells

    summary = GoalSummary(
        gid="g_abc",
        title="Alpha",
        iter_count=12,
        last_phase="tdd_green",
        last_verdict="GREEN",
        sparkline_phases=["tdd_red", "tdd_green"] * 8,  # 16 cells — should cap
        updated_at_iso="2026-04-22T00:00:00+00:00",
    )

    sel = render_fleet_row_cells(summary, selected=True)
    unsel = render_fleet_row_cells(summary, selected=False)

    assert "▶" in sel
    assert "▶" not in unsel
    assert "g_abc" in sel
    assert "Alpha" in sel
    assert "12" in sel  # iter_count
    assert "tdd_green" in sel

    # heat cell glyph count capped at 8 (uses ▇/▆/▅ etc from existing sparkline palette)
    import re
    cells = re.findall(r"[▁▂▃▄▅▆▇█]", sel)
    assert 1 <= len(cells) <= 8, f"expected 1..8 heat cells, got {len(cells)}"
