from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_activity_row_format() -> None:
    from textual.app import App, ComposeResult

    from devboard.tui.activity_row import ActivityRow

    entry = {
        "iter": 3,
        "phase": "tdd_green",
        "verdict_source": "GREEN_CONFIRMED",
        "reasoning": "implemented X",
        "ts": "2026-04-18 12:34:56+00:00",
    }

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield ActivityRow(entry, id="row")

    app = _Host()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        row = app.query_one("#row", ActivityRow)
        header = str(row.header_text)
        assert "12:34" in header, header
        assert "iter 3" in header, header
        assert "tdd_green" in header, header
        assert "GREEN_CONFIRMED" in header, header


@pytest.mark.asyncio
async def test_enter_toggles_expansion() -> None:
    from textual.app import App, ComposeResult

    from devboard.tui.activity_row import ActivityRow

    entry = {"iter": 1, "phase": "tdd_red", "reasoning": "why", "ts": "2026-04-18 01:02:03+00:00"}

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield ActivityRow(entry, id="row")

    app = _Host()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        row = app.query_one("#row", ActivityRow)
        assert row.expanded is False
        row.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert row.expanded is True
