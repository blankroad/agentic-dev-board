from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("diff", ["task_id"], lambda task_id: _run(app, task_id))


def _run(app: "DevBoardApp", task_id: str) -> None:
    from devboard.tui.context_viewer import ContextViewer

    # Locate most recent saved iter_N.diff for the task
    content = f"No diff for task_id={task_id}"
    for goal_dir in (app.store_root / ".devboard" / "goals").glob("*"):
        changes = goal_dir / "tasks" / task_id / "changes"
        if changes.exists():
            diffs = sorted(changes.glob("iter_*.diff"))
            if diffs:
                content = diffs[-1].read_text()
            break

    viewer = app.query_one("#context-viewer", ContextViewer)
    viewer.set_tab_body("diff", content)
    viewer.action_switch("diff")
