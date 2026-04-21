from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Button

from agentboard.tui.command_line import CommandLine


class _SpikeApp(App):
    BINDINGS = [Binding("colon", "open_command_line", "Command")]

    def compose(self) -> ComposeResult:
        yield Button("baseline", id="baseline")
        yield CommandLine(id="command-line")

    def on_mount(self) -> None:
        self.query_one("#baseline", Button).focus()

    def action_open_command_line(self) -> None:
        cl = self.query_one("#command-line", CommandLine)
        cl.open(return_to=self.focused)


@pytest.mark.asyncio
async def test_colon_opens_command_line_esc_blurs_and_restores_focus() -> None:
    app = _SpikeApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        baseline = app.query_one("#baseline", Button)
        cl = app.query_one("#command-line", CommandLine)

        assert app.focused is baseline, f"precondition: expected baseline focused, got {app.focused!r}"

        await pilot.press("colon")
        await pilot.pause()
        assert app.focused is cl, f"after ':': expected CommandLine focused, got {app.focused!r}"

        await pilot.press("escape")
        await pilot.pause()
        assert app.focused is baseline, f"after Esc: expected baseline refocused, got {app.focused!r}"
