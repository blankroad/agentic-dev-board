from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from devboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("runs", [], lambda: _run(app))


def _run(app: "DevBoardApp") -> None:
    runs_list = app.query_one("#resources-runs", ListView)
    runs_list.clear()
    runs_dir = app.store_root / ".devboard" / "runs"
    if not runs_dir.exists():
        runs_list.append(ListItem(Label("(no runs)")))
        return
    files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    for p in files:
        runs_list.append(ListItem(Label(p.stem)))
    runs_list.focus()
