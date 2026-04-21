"""Dev issues pane — wraps the existing dev_timeline_render rollup output
so the previous area/deliverable groupings are preserved below the new
diff viewer, rather than thrown away.
"""

from __future__ import annotations

from textual.widgets import Static

from devboard.tui.dev_timeline_render import render_dev_timeline


_DEV_PHASE_EXACT: frozenset[str] = frozenset({"dev", "eng_review", "iron_law", "rca"})
_DEV_PHASE_PREFIX: tuple[str, ...] = ("tdd_", "tdd")


def _is_dev_phase(phase: str) -> bool:
    if phase in _DEV_PHASE_EXACT:
        return True
    return any(phase.startswith(p) for p in _DEV_PHASE_PREFIX)


def render_issues_pane(payload: dict) -> str:
    """Delegate to the existing dev timeline renderer after filtering to
    dev-phase iters only — matches the legacy `_load_dev_body` invariant
    so review/cso/redteam rows don't leak into the Dev tab."""
    iters = [
        it for it in (payload.get("iterations") or [])
        if _is_dev_phase(str(it.get("phase", "")))
    ]
    try:
        return render_dev_timeline({"iterations": iters})
    except Exception as exc:
        return f"issues pane unavailable: {exc!r}"


class DevIssuesPane(Static):
    def __init__(self, payload: dict | None = None, **kwargs) -> None:
        kwargs.setdefault("markup", False)
        super().__init__(**kwargs)
        self._payload = payload or {}

    def on_mount(self) -> None:
        self.refresh_render()

    def refresh_render(self, payload: dict | None = None) -> None:
        if payload is not None:
            self._payload = payload
        self.update(render_issues_pane(self._payload))
