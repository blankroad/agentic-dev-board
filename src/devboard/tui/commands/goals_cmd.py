from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from devboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("goals", [], lambda: _run(app))


def _run(app: "DevBoardApp") -> None:
    goals_list = app.query_one("#resources-goals", ListView)
    goals_list.clear()
    for goal in app.board.goals:
        goals_list.append(ListItem(Label(f"{goal.status.value[:1]} {goal.title}")))
    goals_list.focus()
