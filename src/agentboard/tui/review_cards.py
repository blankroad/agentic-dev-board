"""Review verdict cards — 4 letter badges (reviewer/cso/redteam/design_review)
showing the latest verdict per reviewer as a letter on a colored background.

Pure-render helper + Static widget wrapper.
"""

from __future__ import annotations

from textual.widgets import Static

from agentboard.tui.verdict_palette import map_verdict

REVIEWER_ORDER: tuple[str, ...] = ("review", "cso", "redteam", "design_review")
REVIEWER_LABELS: dict[str, str] = {
    "review": "reviewer",
    "cso": "cso",
    "redteam": "redteam",
    "design_review": "design",
}


def render_cards(matrix: dict[str, list[tuple[int, str]]]) -> str:
    """Render the 4-reviewer card strip as a Rich-compatible markup string."""
    cells: list[str] = []
    for reviewer in REVIEWER_ORDER:
        events = matrix.get(reviewer, [])
        latest_verdict = events[-1][1] if events else ""
        latest_iter = events[-1][0] if events else None
        letter, color = map_verdict(latest_verdict)
        label = REVIEWER_LABELS[reviewer]
        iter_tag = f" iter{latest_iter}" if latest_iter is not None else ""
        cells.append(f"[{color}]⟦ {letter} ⟧[/] {label}{iter_tag}")
    return "   ".join(cells)


class ReviewCards(Static):
    """Static wrapper so PhaseFlowView can mount and refresh."""

    def __init__(self, matrix: dict | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._matrix = matrix or {}

    def refresh_render(self, matrix: dict | None = None) -> None:
        if matrix is not None:
            self._matrix = matrix
        self.update(render_cards(self._matrix))

    def on_mount(self) -> None:
        self.refresh_render()
