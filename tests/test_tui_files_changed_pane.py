from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_files_changed_pane_lists_touched_files(tmp_path: Path) -> None:
    from textual.app import App, ComposeResult

    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore
    from devboard.tui.files_changed_pane import FilesChangedPane
    from devboard.tui.session_derive import SessionContext

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState()
    board.goals.append(Goal(id="g_f", title="g", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_f"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# p\n")
    task_dir = goal_dir / "tasks" / "t_f"
    changes = task_dir / "changes"
    changes.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_f", "status": "in_progress"}))
    (changes / "iter_2.diff").write_text(
        "+++ b/src/x.py\n+++ b/tests/y.py\n+++ b/docs/z.md\n"
    )

    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield FilesChangedPane(ctx, task_id="t_f", selected_iter=2, id="fc")

    app = _Host()
    async with app.run_test(size=(40, 30)) as pilot:
        await pilot.pause()
        body = app.query_one("#files-changed-body")
        text = str(body.render())
        for path in ("src/x.py", "tests/y.py", "docs/z.md"):
            assert path in text, f"{path} missing in {text!r}"
