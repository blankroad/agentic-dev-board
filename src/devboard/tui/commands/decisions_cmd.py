from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("decisions", ["task_id"], lambda task_id: _run(app, task_id))


def _run(app: "DevBoardApp", task_id: str) -> None:
    from devboard.tui.context_viewer import ContextViewer

    entries = app.store.load_decisions(task_id)
    if not entries:
        body = f"No decisions for task_id={task_id}"
    else:
        body = "\n".join(
            f"[iter {e.iter}] {e.phase} — {e.verdict_source}: {e.reasoning[:80]}"
            for e in entries
        )
    viewer = app.query_one("#context-viewer", ContextViewer)
    viewer.set_tab_body("decisions", body)
    viewer.action_switch("decisions")
