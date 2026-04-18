from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane


TAB_ORDER = ["diff", "decisions", "learnings", "gauntlet", "plan"]

_DEFAULT_PROMPTS: dict[str, str] = {
    "diff": "Type ':diff <task_id>' to load a task's latest iter diff.",
    "decisions": "Type ':decisions <task_id>' to load a task's decision log.",
    "learnings": "Type ':learn <query>' to search saved learnings.",
    "gauntlet": "Select a goal with ':goto <prefix>' — gauntlet artifacts load here.",
    "plan": "Select a goal with ':goto <prefix>' — plan.md loads here.",
}


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
                    yield Static(_DEFAULT_PROMPTS[name], id=f"tab-{name}-body", markup=False)

    def load_active_goal_artifacts(self, store_root: Path, active_goal_id: str | None) -> None:
        """Populate Plan + Gauntlet tabs from the active goal's files. No-op
        if there's no active goal or the files don't exist — the default
        action-prompt stays in place."""
        if not active_goal_id:
            return
        goal_dir = store_root / ".devboard" / "goals" / active_goal_id
        plan_file = goal_dir / "plan.md"
        if plan_file.exists():
            try:
                self.set_tab_body("plan", plan_file.read_text())
            except (OSError, UnicodeDecodeError):
                pass
        gauntlet_dir = goal_dir / "gauntlet"
        if gauntlet_dir.exists():
            parts: list[str] = []
            for step in ("frame", "scope", "arch", "challenge", "decide"):
                f = gauntlet_dir / f"{step}.md"
                if f.exists():
                    try:
                        parts.append(f"── {step}.md ──\n{f.read_text()}")
                    except (OSError, UnicodeDecodeError):
                        continue
            if parts:
                self.set_tab_body("gauntlet", "\n\n".join(parts))

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
