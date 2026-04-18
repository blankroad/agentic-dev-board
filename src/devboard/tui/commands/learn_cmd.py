from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devboard.tui.app import DevBoardApp


def register(app: "DevBoardApp") -> None:
    app.commands.register("learn", ["query"], lambda *query: _run(app, " ".join(query)))


def _run(app: "DevBoardApp", query: str) -> None:
    from devboard.memory.learnings import search_learnings
    from devboard.tui.context_viewer import ContextViewer

    try:
        hits = search_learnings(app.store, query)[:10]
    except Exception as exc:  # noqa: BLE001 — skill API may surface many errors
        hits = []
        body = f"Search failed: {exc}"
    else:
        if not hits:
            body = f"No learnings for '{query}'"
        else:
            body = "\n".join(f"[{l.confidence}] {l.name} — {l.content[:80]}" for l in hits)

    viewer = app.query_one("#context-viewer", ContextViewer)
    viewer.set_tab_body("learnings", body)
    viewer.action_switch("learnings")
