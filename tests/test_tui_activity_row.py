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
async def test_activity_row_verdict_is_colored() -> None:
    """GREEN_CONFIRMED / BROKEN etc. in the header should be rendered as
    colored spans — green for pass, red for broken — so timelines read
    at a glance."""
    from textual.app import App, ComposeResult

    from devboard.tui.activity_row import ActivityRow

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield ActivityRow(
                {"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
                 "ts": "2026-04-18 12:00:00+00:00"},
                id="row-green",
            )
            yield ActivityRow(
                {"iter": 2, "phase": "redteam", "verdict_source": "BROKEN",
                 "ts": "2026-04-18 13:00:00+00:00"},
                id="row-broken",
            )

    app = _Host()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        green_header = app.query_one("#row-green #row-header")
        broken_header = app.query_one("#row-broken #row-header")

        def colors_from(widget) -> set[str]:
            r = widget.render()
            return {
                str(getattr(s, "style", "")).lower()
                for s in getattr(r, "spans", [])
            }

        g_colors = " ".join(colors_from(green_header))
        b_colors = " ".join(colors_from(broken_header))
        assert "green" in g_colors, f"GREEN_CONFIRMED should render green; got {g_colors!r}"
        assert "red" in b_colors, f"BROKEN should render red; got {b_colors!r}"


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
