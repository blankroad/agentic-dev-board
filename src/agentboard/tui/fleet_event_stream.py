"""FleetEventStream — tail-buffer widget for FleetScreen (M2-fleet-tui s_005).

Receives formatted tail events from RunTailWorker via FleetScreen's
on_stream_event hook. Keeps a capped ring of recent events, renders
them as a Static block.
"""
from __future__ import annotations

from textual.widgets import Static

TAIL_CAP = 12


class FleetEventStream(Static):
    """Rolling tail of the last TAIL_CAP formatted events."""

    DEFAULT_CSS = """
    FleetEventStream {
        height: 1fr;
        width: 1fr;
        border: round $primary;
    }
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("markup", True)
        super().__init__(**kwargs)
        self._events: list[tuple[str, str | None]] = []

    def push_event(self, text: str, color: str | None = None) -> None:
        self._events.append((text, color))
        if len(self._events) > TAIL_CAP:
            drop = len(self._events) - TAIL_CAP
            self._events = self._events[drop:]
        self._rerender()

    def _rerender(self) -> None:
        lines: list[str] = []
        for text, color in self._events:
            if color:
                lines.append(f"[{color}]{text}[/]")
            else:
                lines.append(text)
        self.update("\n".join(lines) if lines else "(no events yet)")
