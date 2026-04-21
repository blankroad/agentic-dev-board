from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("diff", ["task_id"], lambda task_id: _run(app, task_id))


def _run(app: "DevBoardApp", task_id: str) -> None:
    """:diff <task_id> updates app._task_id and the reactive selected_iter
    to the latest iter of the given task, which triggers StatusBar +
    PhaseFlowView refresh through the usual watch hooks."""
    # locate latest iter_N.diff for this task under any goal
    latest_iter: int | None = None
    for goal_dir in (app.store_root / ".devboard" / "goals").glob("*"):
        changes = goal_dir / "tasks" / task_id / "changes"
        if changes.exists():
            diffs = sorted(changes.glob("iter_*.diff"))
            if diffs:
                # parse "iter_N.diff" → N
                stem = diffs[-1].stem.removeprefix("iter_")
                try:
                    latest_iter = int(stem)
                except ValueError:
                    latest_iter = None
            break
    cl = app.query_one("#command-line")
    if latest_iter is None:
        cl.value = f"No diff for task_id={task_id}"
        return
    app._task_id = task_id
    app.selected_iter = latest_iter
    app.refresh_for_active_task()
    cl.value = f"diff loaded: task={task_id} iter={latest_iter}"
