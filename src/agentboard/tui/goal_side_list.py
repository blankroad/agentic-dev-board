from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from agentboard.tui.goal_status_legend import LEGEND_INLINE, STATUS_COLOR
from agentboard.tui.goal_tree import build_goal_tree
from agentboard.tui.session_derive import SessionContext


_TASK_RANK = [
    "failed", "blocked", "todo", "planning", "in_progress",
    "reviewing", "awaiting_approval", "converged", "pushed",
]

_STATUS_MARKER: dict[str, str] = {
    "pushed": "✓", "converged": "●", "awaiting_approval": "?",
    "reviewing": "?", "in_progress": "▶", "planning": "·",
    "todo": "○", "blocked": "✗", "failed": "✗",
    "active": "·", "archived": "-",
}

_INDENT = "  "  # two spaces per depth level


def _derive_marker_and_status(goal_dir: Path, declared: str) -> tuple[str, str]:
    """Returns (marker, canonical_status_key). canonical_status_key is
    used for color lookup via STATUS_COLOR."""
    tasks_dir = goal_dir / "tasks"
    statuses: list[str] = []
    if tasks_dir.exists():
        for t_dir in tasks_dir.iterdir():
            task_json = t_dir / "task.json"
            if not task_json.is_file():
                continue
            try:
                data = json.loads(task_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            s = data.get("status")
            if isinstance(s, str):
                statuses.append(s)
    if statuses:
        picked = max(statuses, key=lambda s: _TASK_RANK.index(s) if s in _TASK_RANK else -1)
        return _STATUS_MARKER.get(picked, "·"), picked
    return _STATUS_MARKER.get(declared, "·"), declared


class GoalSideList(Widget):
    """Left sidebar: inline legend line + scrollable goal list with derived
    status markers. Renders a parent_id-based hierarchy via prefix-indent,
    sorts roots by created_at desc, and hides pushed/archived behind the
    '[a] toggle archived' binding."""

    DEFAULT_CSS = """
    GoalSideList { width: 15%; border-right: solid $primary-darken-3; }
    GoalSideList #goal-side-legend {
        padding: 0 1; color: $text-muted; height: 1;
    }
    GoalSideList ListView { height: 1fr; }
    """

    BINDINGS = [
        Binding("a", "toggle_archived", "toggle archived", show=False),
    ]

    class GoalSelected(Message):
        """Emitted when the user clicks/activates a goal in the sidebar.
        App handles this as equivalent to ':goto <goal_id>'."""

        def __init__(self, goal_id: str) -> None:
            super().__init__()
            self.goal_id = goal_id

    def __init__(self, session: SessionContext, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._goal_ids: list[str] = []
        self._show_archived: bool = False

    def compose(self) -> ComposeResult:
        yield Static(LEGEND_INLINE, id="goal-side-legend", markup=True)
        yield ListView(id="resources-goals")

    def on_mount(self) -> None:
        self.refresh_content()

    def action_toggle_archived(self) -> None:
        """Flip the archived-visibility state and re-render."""
        self._show_archived = not self._show_archived
        self.refresh_content()

    def refresh_content(self) -> None:
        """Re-read goals from disk + re-render markers. Call after `:goto`
        or board mutations so markers reflect current task statuses."""
        try:
            lv = self.query_one("#resources-goals", ListView)
        except Exception:
            return
        lv.clear()
        self._goal_ids = []
        rows = build_goal_tree(
            self._session.all_goals(), show_archived=self._show_archived
        )
        for goal, depth in rows:
            goal_dir = (
                self._session.store_root / ".agentboard" / "goals" / goal["id"]
            )
            marker, status_key = _derive_marker_and_status(
                goal_dir, goal.get("status", "active")
            )
            color = STATUS_COLOR.get(status_key, "white")
            title = goal.get("title", goal["id"])
            indent = _INDENT * depth
            lv.append(ListItem(Label(f"{indent}[{color}]{marker}[/] {title}")))
            self._goal_ids.append(goal["id"])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """ListView fires Selected on click or Enter. Post GoalSelected
        so the App can navigate."""
        try:
            idx = list(event.list_view.children).index(event.item)
        except (ValueError, AttributeError):
            return
        if 0 <= idx < len(self._goal_ids):
            self.post_message(self.GoalSelected(self._goal_ids[idx]))
