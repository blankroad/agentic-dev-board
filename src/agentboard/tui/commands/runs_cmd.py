from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("runs", [], lambda: _run(app))


def _run(app: "DevBoardApp") -> None:
    """v2.1: Runs list was removed — the StatusBar now absorbs live run
    info. :runs is kept for backward compat and shows a hint in the
    command line instead of populating a widget."""
    cl = app.query_one("#command-line")
    runs_dir = app.store_root / ".devboard" / "runs"
    count = 0
    if runs_dir.exists():
        count = sum(1 for _ in runs_dir.glob("*.jsonl"))
    cl.value = f"{count} runs on disk — live summary shown in StatusBar"
