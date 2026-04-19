from __future__ import annotations

from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


def _hhmm(ts: str) -> str:
    if not isinstance(ts, str):
        return "--:--"
    if "T" in ts:
        return ts.split("T", 1)[1][:5]
    if " " in ts:
        return ts.split(" ", 1)[1][:5]
    return ts[:5]


class ActivityRow(Widget):
    """Single timeline entry. Header is '[HH:MM] iter N phase verdict';
    body (reasoning + optional files) appears when `expanded` is true."""

    DEFAULT_CSS = """
    ActivityRow { height: auto; padding: 0 1; }
    ActivityRow:focus { background: $primary-darken-3; }
    ActivityRow #row-body { padding: 0 2; color: $text-muted; height: auto; }
    """

    BINDINGS = [Binding("enter", "toggle_and_select", "Open", show=False)]
    can_focus = True

    expanded: reactive[bool] = reactive(False)

    def __init__(self, entry: dict[str, Any], **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.entry = entry

    @property
    def header_text(self) -> str:
        iter_n = self.entry.get("iter", "?")
        phase = self.entry.get("phase", "?")
        verdict = self.entry.get("verdict_source", "")
        ts = _hhmm(str(self.entry.get("ts", "")))
        parts = [f"[{ts}]", f"iter {iter_n}", str(phase)]
        if verdict:
            parts.append(str(verdict))
        return " ".join(parts)

    def compose(self) -> ComposeResult:
        yield Static(self.header_text, id="row-header", markup=False)
        body = Static(str(self.entry.get("reasoning", ""))[:400], id="row-body", markup=False)
        body.display = False
        yield body

    def watch_expanded(self, _old: bool, new: bool) -> None:
        try:
            body = self.query_one("#row-body", Static)
        except Exception:
            return
        body.display = new

    def action_toggle(self) -> None:
        self.expanded = not self.expanded

    class Selected(Message):
        """Emitted when this row is activated (click or Enter). Carries
        the decision entry so the App can update selected_iter."""

        def __init__(self, entry: dict[str, Any]) -> None:
            super().__init__()
            self.entry = entry

    def on_click(self, event: events.Click) -> None:
        self.post_message(self.Selected(self.entry))
        self.expanded = True

    def action_toggle_and_select(self) -> None:
        self.post_message(self.Selected(self.entry))
        self.action_toggle()
