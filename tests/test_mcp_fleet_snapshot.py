"""MCP fleet_snapshot tool test (f_004)."""
from __future__ import annotations

import json


async def test_fleet_snapshot_tool_returns_aggregated_goals(tmp_path) -> None:
    """f_004: agentboard_fleet_snapshot returns {goals, total}."""
    from agentboard.mcp_server import call_tool

    # Seed 2 goals same way as aggregator test
    from tests.test_fleet_aggregator import _seed_goal
    _seed_goal(tmp_path, "g_snap1", "Snap 1", iters=2,
               last_phase="tdd_green", last_verdict="GREEN",
               sparkline=["tdd_red", "tdd_green"])
    _seed_goal(tmp_path, "g_snap2", "Snap 2", iters=5,
               last_phase="review", last_verdict="SURVIVED",
               sparkline=["tdd_green", "redteam"])

    result = await call_tool(
        "agentboard_fleet_snapshot",
        {"project_root": str(tmp_path)},
    )
    payload = json.loads(result[0].text)
    assert payload["total"] == 2
    assert len(payload["goals"]) == 2
    gids = {g["gid"] for g in payload["goals"]}
    assert gids == {"g_snap1", "g_snap2"}
