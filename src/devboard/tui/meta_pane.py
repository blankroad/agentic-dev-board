from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from devboard.tui.goal_status_legend import verdict_color
from devboard.tui.session_derive import SessionContext


class MetaPane(Widget):
    """Right-top key-value summary for the currently selected iter."""

    DEFAULT_CSS = """
    MetaPane { height: auto; padding: 0 1; }
    MetaPane #meta-body { color: $text; }
    """

    def __init__(
        self,
        session: SessionContext,
        task_id: str | None = None,
        selected_iter: int | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._task_id = task_id
        self._selected_iter = selected_iter

    def compose(self) -> ComposeResult:
        yield Static(self._render_text(), id="meta-body", markup=True)

    def refresh_body(self, task_id: str | None, selected_iter: int | None) -> None:
        self._task_id = task_id
        self._selected_iter = selected_iter
        self.query_one("#meta-body", Static).update(self._render_text())

    def _render_text(self) -> str:
        lines: list[str] = []
        lines.append(f"iter:    {self._selected_iter if self._selected_iter is not None else '-'}")
        verdict = "-"
        redteam = "-"
        if self._task_id:
            decisions = self._session.decisions_for_task(self._task_id)
            if self._selected_iter is not None:
                for d in decisions:
                    if d.get("iter") == self._selected_iter:
                        verdict = str(d.get("verdict_source", "-"))
                        break
            for d in decisions:
                if d.get("phase") == "redteam":
                    redteam = str(d.get("verdict_source", "-"))
                    break
        v_col = verdict_color(verdict) if verdict != "-" else "dim"
        r_col = verdict_color(redteam) if redteam != "-" else "dim"
        lines.append(f"verdict: [{v_col}]{verdict}[/]")
        lines.append(f"redteam: [{r_col}]{redteam}[/]")
        lines.append(f"steps:   {self._steps_progress()}")
        return "\n".join(lines)

    def _steps_progress(self) -> str:
        gid = self._session.active_goal_id
        if not gid:
            return "0/0"
        plan_json = (
            self._session.store_root / ".devboard" / "goals" / gid / "plan.json"
        )
        if not plan_json.exists():
            return "0/0"
        try:
            data = json.loads(plan_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return "0/0"
        steps = data.get("atomic_steps", [])
        total = len(steps)
        done = sum(1 for s in steps if isinstance(s, dict) and s.get("completed"))
        return f"{done}/{total}"
