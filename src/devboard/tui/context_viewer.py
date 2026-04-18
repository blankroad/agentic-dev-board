from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane


TAB_ORDER = ["diff", "decisions", "learnings", "gauntlet", "plan"]


class ContextViewer(Widget):
    """Right pane with 5 tabs. v2.0 minimal: each tab is a Static with
    placeholder content; commands replace that content."""

    DEFAULT_CSS = """
    ContextViewer {
        width: 35%;
        border-left: solid $primary-darken-3;
    }
    ContextViewer TabbedContent {
        height: 1fr;
    }
    """

    # Key bindings live on the App so they fire even when focus is elsewhere
    # (but not when CommandLine Input is active — Input consumes printable keys).

    def compose(self) -> ComposeResult:
        with TabbedContent(id="context-tabs", initial="tab-diff"):
            for name in TAB_ORDER:
                with TabPane(name.capitalize(), id=f"tab-{name}"):
                    yield Static(f"({name})", id=f"tab-{name}-body", markup=False)

    def action_switch(self, name: str) -> None:
        self.query_one("#context-tabs", TabbedContent).active = f"tab-{name}"

    def action_cycle(self, step: int) -> None:
        tabs = self.query_one("#context-tabs", TabbedContent)
        active = tabs.active or "tab-diff"
        current = active.removeprefix("tab-")
        idx = (TAB_ORDER.index(current) + step) % len(TAB_ORDER)
        tabs.active = f"tab-{TAB_ORDER[idx]}"

    def set_tab_body(self, name: str, content: str) -> None:
        body = self.query_one(f"#tab-{name}-body", Static)
        body.update(content)
