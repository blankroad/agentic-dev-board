from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentboard.tui.app import DevBoardApp


class GotoError(Exception):
    pass


def register(app: "DevBoardApp") -> None:
    app.commands.register("goto", ["prefix"], lambda prefix: _run(app, prefix))


def _run(app: "DevBoardApp", prefix: str) -> None:
    """v2.1: no match / ambiguous cases surface as a hint in the command
    line instead of stuffing labels into the sidebar ListView. Sidebar
    stays in sync with GoalSideList._goal_ids so click navigation always
    maps to the labeled row."""
    matches = [
        g for g in app.board.goals if g.id.startswith(prefix) or g.title.startswith(prefix)
    ]
    cl = app.query_one("#command-line")
    if not matches:
        cl.value = f"No goal matches '{prefix}'"
        return
    if len(matches) > 1:
        ids = ", ".join(g.id[:10] for g in matches[:5])
        cl.value = f"Ambiguous: {len(matches)} matches — {ids}"
        return
    g = matches[0]
    app._board.active_goal_id = g.id
    app.session.set_active_goal(g.id)
    app.refresh_for_active_goal()
    cl.value = f"→ {g.title}"
