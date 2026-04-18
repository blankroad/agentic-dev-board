from __future__ import annotations


LEGEND_INLINE = "✓ pushed  ▶ wip  ? await  ✗ blocked"

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
