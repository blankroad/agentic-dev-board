from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from devboard.tui.session_derive import SessionContext


class FilesChangedPane(Widget):
    """Right-bottom list of file paths touched by the currently selected
    iter's iter_N.diff."""

    DEFAULT_CSS = """
    FilesChangedPane { height: 1fr; padding: 0 1; border-top: solid $primary-darken-3; }
    FilesChangedPane #files-changed-body { color: $text-muted; }
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
        yield Static(self._render_text(), id="files-changed-body", markup=False)

    def refresh_body(self, task_id: str | None, selected_iter: int | None) -> None:
        self._task_id = task_id
        self._selected_iter = selected_iter
        self.query_one("#files-changed-body", Static).update(self._render_text())

    def _render_text(self) -> str:
        if not self._task_id or self._selected_iter is None:
            return "(no iter selected)"
        files = self._session.files_changed_in_iter(self._task_id, self._selected_iter)
        if not files:
            return "(no files)"
        return "\n".join(files)
