from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("decisions", ["task_id"], lambda task_id: _run(app, task_id))


def _run(app: "DevBoardApp", task_id: str) -> None:
    """v2.1: ContextViewer decisions tab removed. ActivityTimeline renders
    the active task's decisions automatically. :decisions <task_id> now
    switches the App's active task_id and shows a hint."""
    entries = app.store.load_decisions(task_id)
    cl = app.query_one("#command-line")
    if not entries:
        cl.value = f"No decisions for task_id={task_id}"
        return
    app._task_id = task_id
    # update selected_iter to the latest decision's iter so all panes refresh
    latest = max((e.iter for e in entries), default=None)
    if latest is not None:
        app.selected_iter = latest
    cl.value = f"decisions loaded: task={task_id} ({len(entries)} entries)"
