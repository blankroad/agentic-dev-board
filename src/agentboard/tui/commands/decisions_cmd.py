from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("decisions", ["task_id"], lambda task_id: _run(app, task_id))


def _run(app: "DevBoardApp", task_id: str) -> None:
    """v2.1: ContextViewer decisions tab removed. ActivityTimeline renders
    the active task's decisions automatically. :decisions <task_id> now
    switches the App's active task_id and shows a hint."""
    # Switch the task FIRST so widget refresh uses SessionContext (which is
    # resilient to malformed decisions), then show hint via the strict
    # FileStore loader's count.
    app._task_id = task_id
    cl = app.query_one("#command-line")
    # update selected_iter to the latest decision's iter (use SessionContext —
    # it tolerates missing optional fields, unlike FileStore's Pydantic model)
    session_rows = app.session.decisions_for_task(task_id)
    latest = session_rows[0].get("iter") if session_rows else None
    if latest is not None:
        app.selected_iter = latest
    app.refresh_for_active_task()
    if not session_rows:
        cl.value = f"No decisions for task_id={task_id}"
        return
    cl.value = f"decisions loaded: task={task_id} ({len(session_rows)} entries)"
