from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class LiveStreamView(Widget):
    """Center pane: runs/*.jsonl + decisions tail merged stream.
    v2.0 minimal: single Static that can show empty-state or last-line text.

    The body Static uses markup=True so color tags from the anomaly
    classifier are actually rendered (see red-team round 3). Raw user
    content is escape()'d before injection to avoid literal '[' in JSON
    values from being treated as Rich markup.
    """

    DEFAULT_CSS = """
    LiveStreamView {
        width: 45%;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Live Stream — empty", id="live-stream-body", markup=True)

    def set_empty_state(self, message: str) -> None:
        body = self.query_one("#live-stream-body", Static)
        body.update(escape(message))

    def append_line(self, text: str, color: str | None = None) -> None:
        body = self.query_one("#live-stream-body", Static)
        safe = escape(text)
        if color:
            rendered = f"[{color}]{safe}[/]"
        else:
            rendered = safe
        current = str(body.content or "")
        body.update(f"{current}\n{rendered}")
