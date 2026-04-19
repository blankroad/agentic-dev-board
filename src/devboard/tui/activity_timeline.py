from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from devboard.tui.activity_row import ActivityRow
from devboard.tui.session_derive import SessionContext


_MAX_ROWS = 200


class ActivityTimeline(Widget):
    """Collapsible iter-event history. Header shows a one-line summary
    ('▸ Activity  N events  latest: iter N phase verdict'); body reveals
    the full scrollable ActivityRow list when expanded. 't' toggles."""

    DEFAULT_CSS = """
    ActivityTimeline { height: auto; border-top: solid $primary-darken-3; }
    """

    BINDINGS = [Binding("t", "toggle_timeline", "Timeline", show=False)]

    # Mutating this reactive triggers Textual to recompose the widget
    # automatically (handles the async removal + re-mount cycle).
    current_task_id: reactive[str | None] = reactive(None, recompose=True)

    def __init__(
        self, session: SessionContext, task_id: str | None = None, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        self._session = session
        self.set_reactive(ActivityTimeline.current_task_id, task_id)

    def compose(self) -> ComposeResult:
        rows = self._load_rows()
        title = self._summary_title(rows)
        if not rows:
            yield Static(title, id="activity-empty", markup=False)
            return
        with Collapsible(title=title, collapsed=True, id="activity-collapsible"):
            for entry in rows:
                yield ActivityRow(entry)

    def _load_rows(self) -> list[dict]:
        tid = self.current_task_id
        return self._session.decisions_for_task(tid)[:_MAX_ROWS] if tid else []

    def _summary_title(self, rows: list[dict] | None = None) -> str:
        rows = rows if rows is not None else self._load_rows()
        if not rows:
            return "▸ Activity  (no events)"
        latest = rows[0]
        iter_n = latest.get("iter", "?")
        phase = latest.get("phase", "?")
        verdict = latest.get("verdict_source", "")
        tail = f"iter {iter_n} {phase}"
        if verdict:
            tail += f" {verdict}"
        return f"Activity  {len(rows)} events  latest: {tail}"

    def action_toggle_timeline(self) -> None:
        try:
            c = self.query_one("#activity-collapsible", Collapsible)
        except Exception:
            return
        c.collapsed = not c.collapsed

    def refresh_for_task(self, task_id: str | None) -> None:
        """Assign the reactive; Textual schedules recompose automatically."""
        self.current_task_id = task_id
