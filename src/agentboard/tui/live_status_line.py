from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class LiveStatusLine(Widget):
    """Bottom 1-line widget — complementary to top StatusBar. StatusBar
    shows the active goal's curated context; LiveStatusLine streams the
    most recent formatted event from runs/*.jsonl with optional anomaly
    color. Serves as a tail -f feed without reserving a big pane."""

    DEFAULT_CSS = """
    LiveStatusLine {
        dock: bottom;
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }
    LiveStatusLine #live-status-body { color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        yield Static("—", id="live-status-body", markup=True)

    def set_line(self, text: str, color: str | None = None) -> None:
        body = self.query_one("#live-status-body", Static)
        safe = escape(text)
        body.update(f"[{color}]{safe}[/]" if color else safe)
