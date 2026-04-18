from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_collapsible_mounts_on_pinned_textual() -> None:
    """s_001 spike: Textual 8.2.3 provides Collapsible and can mount it
    inside a minimal App. If this fails, ActivityRow falls back to manual
    reactive show/hide (F1 mitigation)."""
    from textual.app import App, ComposeResult
    from textual.widgets import Collapsible, Static

    class _SpikeApp(App):
        def compose(self) -> ComposeResult:
            with Collapsible(title="row 1", collapsed=True, id="c1"):
                yield Static("hidden content", id="inner-1")

    app = _SpikeApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        c = app.query_one("#c1", Collapsible)
        assert c is not None
        assert c.collapsed is True
