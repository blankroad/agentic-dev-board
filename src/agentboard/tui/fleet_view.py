"""FleetView — stub widget for the Fleet surface (M2-fleet-data f_005).

Renders one text row per GoalSummary with a sparkline. No interaction
yet; M2-fleet-tui will add keybindings, heat grid, live event stream,
and DevBoardApp integration.
"""
from __future__ import annotations

from textual.widgets import Static

from agentboard.models import GoalSummary
from agentboard.tui.per_file_scrubber import render_sparkline


def render_fleet_rows(summaries: list[GoalSummary]) -> str:
    """Plain-text render: one row per goal with gid/title/iter/phase/sparkline."""
    if not summaries:
        return "no goals"
    lines: list[str] = []
    for s in summaries:
        # Truncate title for alignment
        title = (s.title or "(untitled)")[:40]
        row = f"{s.gid}  {title:40s}  iter {s.iter_count:>3}  {s.last_phase or '?':<15}  {s.last_verdict or '?':<10}"
        if s.sparkline_phases:
            row += "  " + render_sparkline(s.sparkline_phases)
        lines.append(row)
    return "\n".join(lines)


class FleetView(Static):
    """Stub widget. Renders text rows. No keybindings yet (M2-fleet-tui)."""

    DEFAULT_CSS = """
    FleetView {
        height: auto;
    }
    """

    def __init__(
        self,
        summaries: list[GoalSummary] | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("markup", True)
        super().__init__(**kwargs)
        self._summaries: list[GoalSummary] = summaries or []

    def on_mount(self) -> None:
        self.refresh_render()

    def refresh_render(
        self, summaries: list[GoalSummary] | None = None
    ) -> None:
        if summaries is not None:
            self._summaries = summaries
        self.update(render_fleet_rows(self._summaries))
