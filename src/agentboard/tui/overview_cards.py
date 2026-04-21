"""Overview tab — 4-card metric strip at the top of the Overview pane."""

from __future__ import annotations

from textual.widgets import Static

from agentboard.analytics.overview_metrics import MetricCard


def render_cards(cards: list[MetricCard]) -> str:
    """Render the 4 cards as a single line of labeled bracketed chips."""
    if not cards:
        return "no metrics yet"
    parts: list[str] = []
    for c in cards:
        body = f"{c.label}: {c.value}"
        if c.hint:
            body += f" ({c.hint})"
        parts.append(f"⟦ {body} ⟧")
    return "   ".join(parts)


class OverviewCards(Static):
    def __init__(self, cards: list[MetricCard] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cards = cards or []

    def on_mount(self) -> None:
        self.refresh_render()

    def refresh_render(self, cards: list[MetricCard] | None = None) -> None:
        if cards is not None:
            self._cards = cards
        self.update(render_cards(self._cards))
