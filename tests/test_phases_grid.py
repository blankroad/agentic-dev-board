"""C2: PhasesGrid widget + render_phases_grid pure function."""
from __future__ import annotations

from agentboard.tui.phases_grid import (
    PhasesGrid,
    render_phases_grid,
    phases_grid_from_project,
)


def test_render_phases_grid_empty_shows_message() -> None:
    out = render_phases_grid({"goals": [], "phases_order": []})
    assert "No goals on the board" in out


def test_render_phases_grid_has_header_and_glyphs() -> None:
    snapshot = {
        "phases_order": ["intent", "frame", "lock"],
        "goals": [
            {
                "id": "g_001",
                "title": "First goal",
                "phases": {
                    "intent": "COMPLETED",
                    "frame": "RUNNING",
                    "lock": "NOT_STARTED",
                },
                "latest_event": None,
            },
            {
                "id": "g_002",
                "title": "Blocked goal",
                "phases": {
                    "intent": "COMPLETED",
                    "frame": "BLOCKED",
                    "lock": "NOT_STARTED",
                },
                "latest_event": None,
            },
        ],
    }
    out = render_phases_grid(snapshot)
    # Header contains phase labels
    assert "intent" in out
    assert "frame" in out
    assert "lock" in out
    # Glyphs appear per the state mapping
    assert "✓" in out  # COMPLETED
    assert "⣾" in out  # RUNNING
    assert "⚠" in out  # BLOCKED
    assert "·" in out  # NOT_STARTED


def test_phases_grid_widget_instantiates_with_snapshot() -> None:
    snapshot = {
        "phases_order": ["intent"],
        "goals": [
            {
                "id": "g_001",
                "title": "X",
                "phases": {"intent": "COMPLETED"},
                "latest_event": None,
            }
        ],
    }
    widget = PhasesGrid(snapshot=snapshot)
    assert "✓" in widget._render()


def test_phases_grid_widget_update_snapshot_rerenders() -> None:
    widget = PhasesGrid(snapshot={"goals": [], "phases_order": []})
    assert "No goals" in widget._render()

    widget.update_snapshot({
        "phases_order": ["intent"],
        "goals": [{
            "id": "g_99",
            "title": "Late arrival",
            "phases": {"intent": "RUNNING"},
            "latest_event": None,
        }],
    })
    assert "⣾" in widget._render()
    assert "Late arrival" in widget._render()


def test_phases_grid_from_project_returns_string(tmp_path) -> None:
    # No goals dir → "No goals on the board" fallback
    (tmp_path / ".devboard").mkdir()
    out = phases_grid_from_project(tmp_path)
    assert "No goals" in out
