from __future__ import annotations

from textual import events
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Input


class CommandLine(Input):
    """Bottom-docked command input. Opens on ':' (via host App), closes on Esc."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
    ]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._return_to: Widget | None = None

    def open(self, return_to: Widget | None) -> None:
        self._return_to = return_to
        # Red-team round 3: clear any stale error state so the user starts
        # with a clean input — otherwise typing interleaves with prior
        # error text.
        self.value = ""
        self.styles.background = None
        self.focus()

    def action_close(self) -> None:
        target = self._return_to
        self._return_to = None
        self.value = ""
        if target is not None:
            target.focus()

    async def _on_key(self, event: events.Key) -> None:
        # When ':' is typed while already focused, treat it as 'reset
        # the input' rather than appending ':' to a stale error string.
        # Textual's Input consumes printable chars in _on_key before any
        # Binding fires, so we must intercept here.
        if event.character == ":":
            event.prevent_default()
            event.stop()
            self.value = ""
            self.styles.background = None
            return
        await super()._on_key(event)
