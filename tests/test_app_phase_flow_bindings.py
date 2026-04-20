"""DevBoardApp BINDINGS 1..5 forwarded to PhaseFlowView (s_014)."""

from __future__ import annotations


def test_app_forwards_keys_1_through_5() -> None:
    from devboard.tui.app import DevBoardApp

    key_actions: dict[str, str] = {}
    for b in DevBoardApp.BINDINGS:
        if hasattr(b, "key"):
            key_actions[b.key] = b.action
        elif isinstance(b, tuple):
            key_actions[b[0]] = b[1]

    assert key_actions.get("1") == "phase_flow_tab('overview')"
    assert key_actions.get("2") == "phase_flow_tab('plan')"
    assert key_actions.get("3") == "phase_flow_tab('dev')"
    assert key_actions.get("4") == "phase_flow_tab('result')"
    assert key_actions.get("5") == "phase_flow_tab('review')"
