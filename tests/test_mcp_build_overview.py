"""MCP dispatch tests for devboard_build_overview (s_007)."""

from __future__ import annotations

import json
from pathlib import Path


async def test_devboard_build_overview_tool_registered() -> None:
    from devboard.mcp_server import list_tools

    tools = await list_tools()
    names = [t.name for t in tools]
    assert "devboard_build_overview" in names, (
        f"devboard_build_overview missing from tool registry, got {names!r}"
    )


async def test_devboard_build_overview_dispatch_returns_payload(tmp_path: Path) -> None:
    from devboard.mcp_server import call_tool

    gid = "g_mcp_overview"
    gdir = tmp_path / ".devboard" / "goals" / gid
    gdir.mkdir(parents=True)
    (gdir / "brainstorm.md").write_text(
        "---\ngoal_id: g_mcp_overview\n---\n## Premises\n- MCP dispatch test\n",
        encoding="utf-8",
    )

    result = await call_tool(
        "devboard_build_overview",
        {"project_root": str(tmp_path), "goal_id": gid},
    )
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert payload["purpose"] == "MCP dispatch test"
    assert payload["iterations"] == []
    assert payload["current_state"]["status"] == "awaiting_task"
