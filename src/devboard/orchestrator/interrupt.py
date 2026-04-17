from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class HintMessage:
    text: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "user"


class HintQueue:
    """Thread-safe queue for injecting mid-loop hints from TUI or CLI.

    The graph's plan_node drains this queue and prepends hints to the planner prompt.
    """

    def __init__(self) -> None:
        self._q: queue.Queue[HintMessage] = queue.Queue()
        self._paused = threading.Event()
        self._paused.set()  # not paused initially (set = allowed to run)

    def inject(self, text: str, source: str = "user") -> None:
        self._q.put(HintMessage(text=text, source=source))

    def drain(self) -> list[HintMessage]:
        """Drain all pending hints. Non-blocking."""
        hints = []
        while True:
            try:
                hints.append(self._q.get_nowait())
            except queue.Empty:
                break
        return hints

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    def wait_if_paused(self, timeout: float = 0.1) -> None:
        """Block until resumed. Call at node boundaries."""
        self._paused.wait(timeout=timeout)

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()


# Global singleton — graph nodes import this to check for hints
_global_hint_queue: HintQueue | None = None


def get_hint_queue() -> HintQueue:
    global _global_hint_queue
    if _global_hint_queue is None:
        _global_hint_queue = HintQueue()
    return _global_hint_queue


def reset_hint_queue() -> HintQueue:
    global _global_hint_queue
    _global_hint_queue = HintQueue()
    return _global_hint_queue
