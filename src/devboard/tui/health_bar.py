from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class HealthBar(Widget):
    """Ambient one-line status header: project, branch, iter, verdict, learnings."""

    DEFAULT_CSS = """
    HealthBar {
        height: 1;
        background: $primary-darken-3;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("devboard", id="health-text", markup=False)

    def set_text(self, text: str) -> None:
        self.query_one("#health-text", Static).update(text)

    def flash(self, color: str, duration: float = 1.0) -> None:
        body = self.query_one("#health-text", Static)
        body.styles.background = color
        self.set_timer(duration, lambda: setattr(body.styles, "background", None))
