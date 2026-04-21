"""Review iteration timeline — reviewer × iter grid showing each reviewer's
verdict trajectory across iterations.
"""

from __future__ import annotations

from textual.widgets import Static

from devboard.tui.review_cards import REVIEWER_ORDER, REVIEWER_LABELS
from devboard.tui.verdict_palette import map_verdict

MAX_ITERS_SHOWN: int = 20


def render_timeline(matrix: dict[str, list[tuple[int, str]]]) -> str:
    """Render a text grid of reviewer (rows) × iter (cols) with letter cells.

    Empty matrix → short empty-state string. Iterations beyond the most
    recent 20 are dropped (scrollable viewport handles overflow elsewhere).
    """
    if not matrix:
        return "no reviews yet"

    # Collect iteration universe (union) and trim to latest MAX_ITERS_SHOWN
    all_iters: set[int] = set()
    for events in matrix.values():
        for iter_n, _ in events:
            all_iters.add(iter_n)
    ordered_iters = sorted(all_iters)[-MAX_ITERS_SHOWN:]

    # header row
    header = "          " + " ".join(f"iter{i:<3}" for i in ordered_iters)
    lines = [header]
    for reviewer in REVIEWER_ORDER:
        row_cells = []
        per_iter = dict(matrix.get(reviewer, []))
        for i in ordered_iters:
            verdict = per_iter.get(i, "")
            letter, _ = map_verdict(verdict)
            row_cells.append(f"  {letter}   ")
        label = REVIEWER_LABELS[reviewer]
        lines.append(f"{label:<9} " + "".join(row_cells))
    return "\n".join(lines)


class ReviewTimeline(Static):
    def __init__(self, matrix: dict | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._matrix = matrix or {}

    def refresh_render(self, matrix: dict | None = None) -> None:
        if matrix is not None:
            self._matrix = matrix
        self.update(render_timeline(self._matrix))

    def on_mount(self) -> None:
        self.refresh_render()
