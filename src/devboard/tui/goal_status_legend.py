from __future__ import annotations


# Color per status — used both in the inline legend line and per-goal
# list rows so users can scan state at a glance. Kept semantically
# obvious: green=done, red=broken, yellow=awaiting, blue=active, muted=idle.
STATUS_COLOR: dict[str, str] = {
    "pushed": "green",
    "converged": "cyan",
    "awaiting_approval": "yellow",
    "reviewing": "yellow",
    "await": "yellow",
    "in_progress": "blue",
    "wip": "blue",
    "planning": "magenta",
    "todo": "white",
    "blocked": "red",
    "failed": "red",
    "active": "white",
    "dormant": "dim",
    "archived": "dim",
}


def color_for(label: str) -> str:
    return STATUS_COLOR.get(label, "white")


LEGEND_INLINE = (
    "[green]✓ pushed[/]  [blue]▶ wip[/]  [yellow]? await[/]  [red]✗ blocked[/]"
)

_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("✓", "pushed", "task pushed / done"),
    ("●", "converged", "loop converged, awaiting approval"),
    ("?", "await", "awaiting approval / review"),
    ("▶", "wip", "in_progress / active work"),
    ("○", "todo", "not started"),
    ("✗", "blocked", "blocked or failed"),
    ("·", "dormant", "no tasks / inert"),
)


def entries() -> tuple[tuple[str, str, str], ...]:
    """Returns (marker, label, summary) tuples for HelpModal injection."""
    return _ENTRIES
