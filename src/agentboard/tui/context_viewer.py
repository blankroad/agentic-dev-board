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
        width: 80%;
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
        """Populate Plan + Gauntlet tabs from the active goal's files, and
        Diff + Decisions tabs from the most-recent task under that goal.
        No-op for missing files — the default action-prompt stays in place."""
        if not active_goal_id:
            return
        goal_dir = store_root / ".agentboard" / "goals" / active_goal_id
        plan_file = goal_dir / "plan.md"
        if plan_file.exists():
            try:
                self.set_tab_body("plan", plan_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
        gauntlet_dir = goal_dir / "phases"
        if gauntlet_dir.exists():
            parts: list[str] = []
            for step in ("frame", "scope", "arch", "challenge", "decide"):
                f = gauntlet_dir / f"{step}.md"
                if f.exists():
                    try:
                        parts.append(f"── {step}.md ──\n{f.read_text(encoding='utf-8')}")
                    except (OSError, UnicodeDecodeError):
                        continue
            if parts:
                self.set_tab_body("gauntlet", "\n\n".join(parts))

        # Most-recent task under this goal: pick by task dir mtime
        tasks_dir = goal_dir / "tasks"
        if not tasks_dir.exists():
            return
        task_dirs = [p for p in tasks_dir.iterdir() if p.is_dir()]
        if not task_dirs:
            return
        latest = max(task_dirs, key=lambda p: p.stat().st_mtime)

        diffs = sorted((latest / "changes").glob("iter_*.diff")) if (latest / "changes").exists() else []
        if diffs:
            try:
                self.set_tab_body("diff", diffs[-1].read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass

        decisions_file = latest / "decisions.jsonl"
        if decisions_file.exists():
            import json

            lines: list[str] = []
            try:
                raw = decisions_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                raw = ""
            for raw_line in raw.splitlines():
                if not raw_line.strip():
                    continue
                try:
                    d = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                itr = d.get("iter", "?")
                phase = d.get("phase", "?")
                verdict = d.get("verdict_source", "")
                reasoning = str(d.get("reasoning", ""))[:80]
                lines.append(f"[iter {itr}] {phase} — {verdict}: {reasoning}")
            if lines:
                self.set_tab_body("decisions", "\n".join(lines))

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
        if name in ("plan", "gauntlet"):
            from rich.markdown import Markdown

            body.update(Markdown(content))
        else:
            body.update(content)
