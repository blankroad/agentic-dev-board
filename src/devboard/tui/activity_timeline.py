from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget

from devboard.tui.activity_row import ActivityRow
from devboard.tui.session_derive import SessionContext


_MAX_ROWS = 200


class ActivityTimeline(Widget):
    """Scrollable list of ActivityRow widgets, newest-first, capped at 200
    rows to bound growth."""

    DEFAULT_CSS = """
    ActivityTimeline { height: 1fr; border-top: solid $primary-darken-3; }
    ActivityTimeline VerticalScroll { height: 1fr; }
    """

    def __init__(
        self, session: SessionContext, task_id: str | None = None, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._task_id = task_id

    def compose(self) -> ComposeResult:
        rows: list[ActivityRow] = []
        if self._task_id:
            for entry in self._session.decisions_for_task(self._task_id)[:_MAX_ROWS]:
                rows.append(ActivityRow(entry))
        with VerticalScroll(id="timeline-scroll"):
            for row in rows:
                yield row
