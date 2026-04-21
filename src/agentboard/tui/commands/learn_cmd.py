from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("learn", ["query"], lambda *query: _run(app, " ".join(query)))


def _run(app: "DevBoardApp", query: str) -> None:
    """v2.1: Learnings tab removed. :learn <query> shows a count hint in
    the command line (full render deferred until a dedicated pane in v2.2)."""
    from agentboard.memory.learnings import search_learnings

    cl = app.query_one("#command-line")
    try:
        hits = search_learnings(app.store, query)[:10]
    except Exception as exc:  # noqa: BLE001 — search API surfaces varied errors
        cl.value = f"Search failed: {exc}"
        return
    if not hits:
        cl.value = f"No learnings for '{query}'"
        return
    top = hits[0]
    cl.value = f"{len(hits)} learning(s) — top: {top.name}"
