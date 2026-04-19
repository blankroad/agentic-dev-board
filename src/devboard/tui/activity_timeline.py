from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Collapsible, Static

from devboard.tui.activity_row import ActivityRow
from devboard.tui.session_derive import SessionContext


_MAX_ROWS = 200


class ActivityTimeline(Collapsible):
    """Collapsible iter-event history. Header shows a one-line summary
    ('▸ Activity  N events  latest: iter N phase verdict'); body reveals
    the full scrollable ActivityRow list when expanded. 't' toggles."""

    DEFAULT_CSS = """
    ActivityTimeline { height: auto; border-top: solid $primary-darken-3; }
    """

    BINDINGS = [Binding("t", "toggle_timeline", "Timeline", show=False)]

    def __init__(
        self, session: SessionContext, task_id: str | None = None, **kwargs: object
    ) -> None:
        self._session = session
        self._task_id = task_id
        rows = []
        if task_id:
            rows = session.decisions_for_task(task_id)[:_MAX_ROWS]
        self._rows = rows
        title = self._summary_title()
        super().__init__(title=title, collapsed=True, **kwargs)

    def compose(self) -> ComposeResult:
        if not self._rows:
            yield Static("(no activity yet)", id="timeline-empty", markup=False)
            return
        for entry in self._rows:
            yield ActivityRow(entry)

    def _summary_title(self) -> str:
        if not self._rows:
            return "▸ Activity  (no events)"
        latest = self._rows[0]
        iter_n = latest.get("iter", "?")
        phase = latest.get("phase", "?")
        verdict = latest.get("verdict_source", "")
        tail = f"iter {iter_n} {phase}"
        if verdict:
            tail += f" {verdict}"
        return f"▸ Activity  {len(self._rows)} events  latest: {tail}"

    def action_toggle_timeline(self) -> None:
        self.collapsed = not self.collapsed
