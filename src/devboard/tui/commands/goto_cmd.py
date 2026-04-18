from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from devboard.tui.app import DevBoardApp


class GotoError(Exception):
    pass


def register(app: "DevBoardApp") -> None:
    app.commands.register("goto", ["prefix"], lambda prefix: _run(app, prefix))


def _run(app: "DevBoardApp", prefix: str) -> None:
    matches = [g for g in app.board.goals if g.id.startswith(prefix) or g.title.startswith(prefix)]
    goals_list = app.query_one("#resources-goals", ListView)
    goals_list.clear()

    if not matches:
        goals_list.append(ListItem(Label(f"No match for '{prefix}'")))
        return
    if len(matches) > 1:
        goals_list.append(ListItem(Label(f"Ambiguous: {len(matches)} matches")))
        for g in matches:
            goals_list.append(ListItem(Label(f"  {g.id[:10]} {g.title}")))
        return

    # Exactly one
    g = matches[0]
    app._board.active_goal_id = g.id
    goals_list.append(ListItem(Label(f"> {g.status.value[:1]} {g.title}")))
    for other in app.board.goals:
        if other.id != g.id:
            goals_list.append(ListItem(Label(f"  {other.status.value[:1]} {other.title}")))
    goals_list.focus()
