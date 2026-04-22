"""FleetView — plain-text stub (M2-fleet-data) + FleetListPane widget
(M2-fleet-tui).

`render_fleet_rows` is kept for back-compat and non-Textual callers.
`FleetListPane` is the interactive k9s-style row navigator used by
FleetScreen: reactive selected_index, ↓/↑ keybindings, / filter.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from agentboard.models import GoalSummary
from agentboard.tui.fleet_row_render import render_fleet_row_cells
from agentboard.tui.per_file_scrubber import render_sparkline


def render_fleet_rows(summaries: list[GoalSummary]) -> str:
    """Plain-text render: one row per goal with gid/title/iter/phase/sparkline.

    Back-compat helper from M2-fleet-data. Not used by FleetListPane.
    """
    if not summaries:
        return "no goals"
    lines: list[str] = []
    for s in summaries:
        title = (s.title or "(untitled)")[:40]
        row = (
            f"{s.gid}  {title:40s}  iter {s.iter_count:>3}  "
            f"{s.last_phase or '?':<15}  {s.last_verdict or '?':<10}"
        )
        if s.sparkline_phases:
            row += "  " + render_sparkline(s.sparkline_phases)
        lines.append(row)
    return "\n".join(lines)


class FleetView(Static):
    """Legacy stub widget — kept for any caller still importing it.
    New code should use FleetListPane instead."""

    DEFAULT_CSS = """
    FleetView { height: auto; }
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
        self.update(render_fleet_rows(self._summaries))


class FleetListPane(Widget):
    """Interactive fleet row navigator. Reactive selected_index drives
    render. Filter narrows visible rows by (title+gid) substring."""

    DEFAULT_CSS = """
    FleetListPane {
        height: 1fr;
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("down", "move_down", "down", show=False),
        Binding("up", "move_up", "up", show=False),
    ]

    can_focus = True

    selected_index: reactive[int | None] = reactive(None)

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("markup", True)
        super().__init__(**kwargs)
        self._rows: list[GoalSummary] = []
        self._filter_query: str = ""

    def set_rows(self, rows: list[GoalSummary]) -> None:
        self._rows = list(rows)
        self.selected_index = 0 if self._rows else None
        self.refresh()

    def set_filter(self, query: str) -> None:
        self._filter_query = query or ""
        visible = self._visible_rows()
        if not visible:
            self.selected_index = None
        elif self.selected_index is None or self.selected_index >= len(visible):
            self.selected_index = 0
        self.refresh()

    def action_move_down(self) -> None:
        visible = self._visible_rows()
        if not visible:
            return
        if self.selected_index is None:
            self.selected_index = 0
            return
        self.selected_index = min(self.selected_index + 1, len(visible) - 1)

    def action_move_up(self) -> None:
        visible = self._visible_rows()
        if not visible:
            return
        if self.selected_index is None:
            self.selected_index = 0
            return
        self.selected_index = max(self.selected_index - 1, 0)

    def _visible_rows(self) -> list[GoalSummary]:
        if not self._filter_query:
            return self._rows
        q = self._filter_query.lower()
        return [r for r in self._rows if q in (r.title + r.gid).lower()]

    def render(self) -> str:
        visible = self._visible_rows()
        if not visible:
            return "no goals" if not self._filter_query else "no matches"
        lines = []
        for i, s in enumerate(visible):
            lines.append(render_fleet_row_cells(s, selected=(i == self.selected_index)))
        return "\n".join(lines)
