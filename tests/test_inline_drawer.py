"""InlineDrawer Pilot tests (M1b m_009, m_010, m_011).

Critical TUI prototype — Eng review F1 flagged Collapsible+await mount()
as flakiness risk. Tests assert mount completion + focus management +
one-at-a-time enforcement.
"""
from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Static


class _DrawerHost(App):
    """Minimal host app for testing InlineDrawer behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.last_focus_target: object = None

    def compose(self) -> ComposeResult:
        from agentboard.tui.inline_drawer import DrawerContainer
        yield Vertical(
            Button("trigger-a", id="trigger-a"),
            Button("trigger-b", id="trigger-b"),
            DrawerContainer(id="drawer-container"),
            id="root",
        )


async def test_inline_drawer_mount_and_focus() -> None:
    """m_009: opening drawer mounts content and shifts focus into drawer."""
    from agentboard.tui.inline_drawer import DrawerContainer

    app = _DrawerHost()
    async with app.run_test() as pilot:
        # Focus initial trigger
        trig = app.query_one("#trigger-a", Button)
        trig.focus()
        await pilot.pause()

        container = app.query_one("#drawer-container", DrawerContainer)
        await container.open(content_widget=Static("drawer-content", id="dc"), trigger=trig)
        await pilot.pause()

        # Drawer content present in DOM
        contents = app.query("#dc")
        assert len(contents) == 1, "drawer content not mounted"


async def test_inline_drawer_one_at_a_time() -> None:
    """m_010: opening B closes A within same DrawerContainer scope."""
    from agentboard.tui.inline_drawer import DrawerContainer

    app = _DrawerHost()
    async with app.run_test() as pilot:
        trig_a = app.query_one("#trigger-a", Button)
        trig_b = app.query_one("#trigger-b", Button)
        container = app.query_one("#drawer-container", DrawerContainer)

        await container.open(Static("drawer-A", id="dA"), trigger=trig_a)
        await pilot.pause()
        assert len(app.query("#dA")) == 1

        await container.open(Static("drawer-B", id="dB"), trigger=trig_b)
        await pilot.pause()
        # A should be gone, B present
        assert len(app.query("#dA")) == 0, "drawer A still open after B opened"
        assert len(app.query("#dB")) == 1, "drawer B not present"


async def test_inline_drawer_close_restores_focus() -> None:
    """m_011: close drawer restores focus to triggering widget."""
    from agentboard.tui.inline_drawer import DrawerContainer

    app = _DrawerHost()
    async with app.run_test() as pilot:
        trig = app.query_one("#trigger-a", Button)
        trig.focus()
        await pilot.pause()
        assert app.focused is trig

        container = app.query_one("#drawer-container", DrawerContainer)
        await container.open(Static("drawer-X", id="dX"), trigger=trig)
        await pilot.pause()

        await container.close()
        await pilot.pause()
        # Focus restored to trigger
        assert app.focused is trig, (
            f"focus not restored to trigger; got {app.focused!r}"
        )
        # Drawer content removed
        assert len(app.query("#dX")) == 0
