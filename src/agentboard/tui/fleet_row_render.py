"""Pure render helpers for FleetScreen rows (M2-fleet-tui s_001).

Kept free of Textual widget imports so it can be unit-tested in pure
Python and composed by FleetListPane without Rich-text fiddling
leaking into widget logic.
"""
from __future__ import annotations

from agentboard.models import GoalSummary
from agentboard.tui.tui_tokens import color_for_phase

HEAT_GLYPH = "▇"
HEAT_MAX_CELLS = 8


def render_heat_cells(phases: list[str]) -> str:
    """Render up to HEAT_MAX_CELLS colored block cells from the TAIL
    of phases (most recent N). Returns Rich markup string; empty if
    phases is empty.
    """
    if not phases:
        return ""
    tail = phases[-HEAT_MAX_CELLS:]
    return "".join(f"[{color_for_phase(p)}]{HEAT_GLYPH}[/]" for p in tail)


def render_fleet_row_cells(summary: GoalSummary, selected: bool = False) -> str:
    """Render one fleet row as a Rich-markup string.

    Format: `▶ gid  title  iter N  phase  heatcells` (marker only when selected).
    heatcells tail-caps at HEAT_MAX_CELLS so terminal width stays predictable.
    """
    marker = "▶ " if selected else "  "
    title = (summary.title or "(untitled)")[:40]
    phase = summary.last_phase or "?"
    heat = render_heat_cells(summary.sparkline_phases)
    return (
        f"{marker}{summary.gid}  {title:40s}  "
        f"iter {summary.iter_count:>3}  {phase:<15}  {heat}"
    )
