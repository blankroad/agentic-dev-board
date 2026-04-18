from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, ListView


class ResourcesView(Widget):
    """Left sidebar: goals list + recent runs. Minimal v2.0 stub."""

    DEFAULT_CSS = """
    ResourcesView {
        width: 20%;
        border-right: solid $primary-darken-3;
    }
    ResourcesView Label.section {
        background: $primary-darken-3;
        padding: 0 1;
    }
    ResourcesView ListView {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Goals", classes="section")
        yield ListView(id="resources-goals")
        yield Label("Runs", classes="section")
        yield ListView(id="resources-runs")
