"""Dev tab compose includes DrawerContainer (M1b-extra x_004)."""
from __future__ import annotations

import pytest


async def test_phase_flow_dev_tab_includes_drawer_container(tmp_path) -> None:
    """x_004: PhaseFlowView's Dev tab compose yields a DrawerContainer
    reachable via query from the mounted app.
    """
    from textual.app import App, ComposeResult

    from agentboard.tui.inline_drawer import DrawerContainer
    from agentboard.tui.phase_flow import PhaseFlowView
    from agentboard.tui.session_derive import SessionContext

    class _Host(App):
        def compose(self) -> ComposeResult:
            session = SessionContext(tmp_path)
            yield PhaseFlowView(session, task_id=None, id="phase-flow")

    app = _Host()
    async with app.run_test() as pilot:
        # Navigate to Dev tab
        phase_flow = app.query_one("#phase-flow", PhaseFlowView)
        phase_flow.action_activate_tab("dev")
        await pilot.pause()

        # DrawerContainer must be present somewhere under Dev TabPane
        drawers = app.query(DrawerContainer)
        assert len(drawers) >= 1, "DrawerContainer not found in Dev tab compose"
