from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_status_bar_renders_all_segments() -> None:
    from textual.app import App, ComposeResult

    from devboard.tui.status_bar import StatusBar

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield StatusBar(id="sb")

    app = _Host()
    async with app.run_test(size=(140, 10)) as pilot:
        await pilot.pause()
        sb = app.query_one("#sb", StatusBar)
        sb.set_segments(goal_title="TUI v2.1", iter_n=3, phase="tdd_green", redteam="SURVIVED", tests=408)
        await pilot.pause()
        body = app.query_one("#status-bar-body")
        text = str(body.render())
        assert "● TUI v2.1" in text, text
        assert "▶ iter 3" in text, text
        assert "tdd_green" in text, text
        assert "SURVIVED" in text, text
        assert "408" in text, text
