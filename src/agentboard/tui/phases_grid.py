"""C2 Phases grid — k9s-style goals × phases matrix widget.

Renders the output of `agentboard.analytics.phases_snapshot.phases_snapshot()`
as a compact grid. Rows = goals, columns = D1 phases, cells = phase state
glyph. Designed to drop into the existing TUI app as a new tab / widget.

Row format:
    {goal_id[:12]:12s} {title[:30]:30s} | intent frame arch stress lock exec pr apprvl

Cell glyph:
    ✓  COMPLETED
    ⣾  RUNNING
    ⚠  BLOCKED
    ·  NOT_STARTED

The widget is a `Static` so it composes trivially. Live updates happen via
`refresh(snapshot=...)`; the widget is pure render given a snapshot dict.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.widgets import Static


_STATE_GLYPH = {
    "COMPLETED": "✓",
    "RUNNING": "⣾",
    "BLOCKED": "⚠",
    "NOT_STARTED": "·",
}

# Short labels for phase columns — fit in 7 chars for compactness.
_PHASE_LABELS = {
    "intent": "intent",
    "frame": "frame",
    "architecture": "arch",
    "stress": "stress",
    "lock": "lock",
    "execute": "exec",
    "parallel_review": "pr",
    "approval": "apprvl",
}


def render_phases_grid(snapshot: dict[str, Any]) -> str:
    """Render a phases_snapshot dict as plain text. Pure function — easy
    to unit-test without mounting a Textual app."""
    phases_order = snapshot.get("phases_order", [])
    goals = snapshot.get("goals", [])

    if not goals:
        return "No goals on the board."

    # Header
    col_widths = [max(len(_PHASE_LABELS.get(p, p)), 3) for p in phases_order]
    header_cols = "  ".join(
        f"{_PHASE_LABELS.get(p, p):^{w}}" for p, w in zip(phases_order, col_widths)
    )
    header = f"{'goal_id':12s}  {'title':30s}  {header_cols}"
    sep = "-" * len(header)

    lines = [header, sep]

    for goal in goals:
        goal_id_trunc = goal["id"][:12]
        title_trunc = (goal.get("title") or "")[:30]
        cells = "  ".join(
            f"{_STATE_GLYPH.get(goal['phases'].get(p, 'NOT_STARTED'), '?'):^{w}}"
            for p, w in zip(phases_order, col_widths)
        )
        lines.append(f"{goal_id_trunc:12s}  {title_trunc:30s}  {cells}")

    return "\n".join(lines)


class PhasesGrid(Static):
    """Textual widget wrapping `render_phases_grid`. Hold a snapshot;
    re-render on `update_snapshot(new_snapshot)` calls."""

    DEFAULT_CSS = """
    PhasesGrid {
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, snapshot: dict[str, Any] | None = None, **kwargs) -> None:
        self._snapshot = snapshot or {"goals": [], "phases_order": []}
        super().__init__(self._render(), **kwargs)

    def _render(self) -> str:
        return render_phases_grid(self._snapshot)

    def update_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Replace the snapshot and re-render."""
        self._snapshot = snapshot
        self.update(self._render())


def phases_grid_from_project(project_root: Path | str) -> str:
    """Convenience: load a snapshot + render as plain text in one call.
    Used by the MCP wrapper + CLI/TUI quick-view command."""
    from agentboard.analytics.phases_snapshot import phases_snapshot

    return render_phases_grid(phases_snapshot(project_root))
