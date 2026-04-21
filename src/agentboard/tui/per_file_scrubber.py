"""PerFileScrubber widget — sparkline strip showing per-file phase
history (M1b m_005, m_006, m_007).

The scrubber appears next to each row in DevFileTree. One cell per
iter that touched the file. Color from tui_tokens.color_for_phase.
Click on a cell dispatches ScrubberSegmentClicked(file_path, iter_n)
message that phase_flow.py handler converts into an InlineDrawer open.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.message import Message
from textual.widget import Widget
from textual import events

from agentboard.tui.tui_tokens import color_for_phase

# Maximum visible cells in a sparkline. Above this, segments are
# aggregated by averaging contiguous groups (most-common phase wins).
MAX_CELLS = 30
GLYPH = "▇"


def render_sparkline(phases: list[str]) -> str:
    """Render a phase-marker list as a colored cell strip.

    Returns a Rich-compatible markup string. For len > MAX_CELLS,
    aggregates contiguous groups so output cells <= MAX_CELLS.
    """
    if not phases:
        return ""
    # Aggregate when needed
    cells_phases = _aggregate(phases, MAX_CELLS)
    parts: list[str] = []
    for phase in cells_phases:
        color = color_for_phase(phase)
        parts.append(f"[{color}]{GLYPH}[/]")
    return "".join(parts)


def _aggregate(phases: list[str], max_cells: int) -> list[str]:
    """Bucket phases into <= max_cells groups, picking most-common per group."""
    n = len(phases)
    if n <= max_cells:
        return phases
    # Each group spans approximately n / max_cells items
    group_size = n / max_cells
    out: list[str] = []
    for i in range(max_cells):
        start = int(i * group_size)
        end = int((i + 1) * group_size)
        if end > n:
            end = n
        bucket = phases[start:end]
        if not bucket:
            continue
        # Most common phase wins (tie → first occurrence)
        counts: dict[str, int] = {}
        for p in bucket:
            counts[p] = counts.get(p, 0) + 1
        best = max(counts.items(), key=lambda kv: kv[1])[0]
        out.append(best)
    return out


def segment_index_for_x(x: int, total_cells: int, width: int) -> int:
    """Map a click x-coordinate to a segment (cell) index.

    Clamps to [0, total_cells-1]. `width` is total render width in cells.
    """
    if total_cells <= 0:
        return 0
    if x < 0:
        return 0
    if x >= width:
        return total_cells - 1
    # Each cell occupies width / total_cells x-positions
    cell_width = max(width / total_cells, 1)
    idx = int(x / cell_width)
    if idx >= total_cells:
        idx = total_cells - 1
    return idx


@dataclass
class ScrubberSegmentClicked(Message):
    """Posted when a user clicks a segment in PerFileScrubber."""

    file_path: str
    iter_n: int


class PerFileScrubber(Widget):
    """Per-row sparkline widget for DevFileTree.

    DEFAULT_CSS keeps the widget on a single line. Click handler maps
    pixel x → segment index → iter_n via stored phases.
    """

    DEFAULT_CSS = """
    PerFileScrubber {
        height: 1;
        width: auto;
    }
    """

    can_focus = True

    def __init__(
        self,
        file_path: str,
        phases: list[str] | None = None,
        iter_offsets: list[int] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._file_path = file_path
        self._phases = phases or []
        # iter_offsets[i] = the iter_n that segment i (post-aggregation)
        # maps to. If not provided, default to 1..len(phases).
        self._iter_offsets = iter_offsets

    def render(self) -> str:
        return render_sparkline(self._phases)

    def on_click(self, event: events.Click) -> None:
        # Compute the segment from x. Aggregation may collapse
        # multiple iters into one cell; we report the iter at the
        # midpoint of the aggregated bucket.
        n_visible = min(len(self._phases), MAX_CELLS)
        if n_visible == 0:
            return
        # Width approximation: 1 char per visible cell
        width = max(n_visible, 1)
        idx = segment_index_for_x(event.x, n_visible, width)
        if self._iter_offsets and 0 <= idx < len(self._iter_offsets):
            iter_n = self._iter_offsets[idx]
        else:
            # Fallback: assume 1-based iter_n matching phase index
            n_total = len(self._phases)
            if n_total <= MAX_CELLS:
                iter_n = idx + 1
            else:
                # Map idx → midpoint of source bucket
                group_size = n_total / MAX_CELLS
                iter_n = int((idx + 0.5) * group_size) + 1
        self.post_message(ScrubberSegmentClicked(self._file_path, iter_n))
