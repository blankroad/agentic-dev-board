"""FleetView widget tests — M2-fleet-data stub + M2-fleet-tui FleetListPane."""
from __future__ import annotations


def _summaries():
    from agentboard.models import GoalSummary
    return [
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


def test_fleet_view_renders_rows_from_summaries() -> None:
    """f_005: plain-text render helper still works (back-compat with M2-fleet-data)."""
    from agentboard.tui.fleet_view import render_fleet_rows

    output = render_fleet_rows(_summaries())
    assert "g_a" in output and "Alpha" in output
    assert "g_b" in output and "Beta" in output
    assert "3" in output and "7" in output
    assert "▇" in output


def test_fleet_list_pane_set_rows_initial_selection() -> None:
    """s_002: set_rows updates rows + selects index 0 for non-empty, None for empty."""
    from agentboard.tui.fleet_view import FleetListPane

    pane = FleetListPane()
    assert pane.selected_index is None  # no rows yet

    pane.set_rows(_summaries())
    assert pane.selected_index == 0
    assert len(pane._rows) == 2

    pane.set_rows([])
    assert pane.selected_index is None
    assert pane._rows == []


def test_fleet_list_pane_move_actions_clamped() -> None:
    """s_003: action_move_down/up clamps at bounds without wrapping."""
    from agentboard.tui.fleet_view import FleetListPane

    pane = FleetListPane()
    pane.set_rows(_summaries())  # 2 rows

    assert pane.selected_index == 0
    pane.action_move_down()
    assert pane.selected_index == 1
    pane.action_move_down()  # clamp
    assert pane.selected_index == 1
    pane.action_move_up()
    assert pane.selected_index == 0
    pane.action_move_up()  # clamp
    assert pane.selected_index == 0

    # empty rows → actions no-op
    pane.set_rows([])
    pane.action_move_down()
    pane.action_move_up()
    assert pane.selected_index is None


def test_fleet_list_pane_set_filter_substring() -> None:
    """s_004: set_filter narrows rows by (title + gid) substring, case-insensitive."""
    from agentboard.tui.fleet_view import FleetListPane

    pane = FleetListPane()
    pane.set_rows(_summaries())

    pane.set_filter("alpha")
    assert len(pane._visible_rows()) == 1
    assert pane._visible_rows()[0].gid == "g_a"

    pane.set_filter("g_b")
    assert len(pane._visible_rows()) == 1
    assert pane._visible_rows()[0].gid == "g_b"

    pane.set_filter("")  # unfiltered
    assert len(pane._visible_rows()) == 2

    pane.set_filter("XYZ_NO_MATCH")
    assert pane._visible_rows() == []
