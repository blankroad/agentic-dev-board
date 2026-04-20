"""MCP dispatch tests for devboard_generate_narrative.

Goal: g_20260420_032908_54200a. Ensures the new MCP tool is
discoverable via list_tools() and produces a plan_summary.md when
dispatched through call_tool(). Separate test covers approval-skill
wiring (Step 4.5 conditional).
"""

from __future__ import annotations

import json
from pathlib import Path


async def test_mcp_server_registers_generate_narrative() -> None:
    """list_tools() must include devboard_generate_narrative so MCP
    clients (Claude Code) can discover and call it."""
    from devboard.mcp_server import list_tools

    tools = await list_tools()
    names = [t.name for t in tools]

    assert "devboard_generate_narrative" in names, (
        f"devboard_generate_narrative missing from tool registry, got {names!r}"
    )


async def test_mcp_generate_narrative_dispatch_returns_plan_summary_path(
    tmp_path: Path,
) -> None:
    """call_tool('devboard_generate_narrative', {...}) must execute the
    generator against a tmp_path fixture goal and return a dict whose
    plan_summary_path points at an existing file."""
    from devboard.mcp_server import call_tool

    goal_id = "g_mcp_fixture"
    goal_dir = tmp_path / ".devboard" / "goals" / goal_id
    task_dir = goal_dir / "tasks" / "t_fix"
    task_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text(
        "## Problem\n\nP\n\n"
        "## Architecture\n\nA\n\n"
        "## Scope Decision\n\nHOLD\n\n"
        "## Budget\n\n- tok: 1\n",
        encoding="utf-8",
    )
    (task_dir / "decisions.jsonl").write_text(
        '{"iter": 1, "phase": "tdd_green", "reasoning": "g", "verdict_source": "GREEN"}\n',
        encoding="utf-8",
    )

    result = await call_tool(
        "devboard_generate_narrative",
        {"project_root": str(tmp_path), "goal_id": goal_id},
    )

    # MCP dispatch wraps payload in a list[TextContent]; our convention
    # (see _text helper) is single TextContent with JSON body.
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert "plan_summary_path" in payload, (
        f"missing plan_summary_path in MCP response, got {payload!r}"
    )
    out_file = Path(payload["plan_summary_path"])
    assert out_file.exists()
    assert out_file.name == "plan_summary.md"


def test_approval_step_4_5_invokes_generator_when_ui_surface_true() -> None:
    """Documentation integration: skills/devboard-approval/SKILL.md must
    reference the new generator tool in Step 4.5 under a ui_surface
    guard, wrapped in try/except per challenge.md failure-mode #3."""
    skill_md = (
        Path(__file__).resolve().parent.parent
        / "skills"
        / "devboard-approval"
        / "SKILL.md"
    )
    assert skill_md.exists(), f"approval SKILL.md not found at {skill_md}"

    text = skill_md.read_text(encoding="utf-8")
    assert "devboard_generate_narrative" in text, (
        "SKILL.md Step 4.5 does not reference devboard_generate_narrative"
    )
    assert "ui_surface" in text, (
        "SKILL.md Step 4.5 is not gated by ui_surface"
    )
    # Best-effort pattern: try/except wrapping the call so generator
    # failure does not block approval (challenge.md HIGH finding #3).
    assert "try" in text and "except" in text, (
        "SKILL.md Step 4.5 must wrap the generator call in try/except "
        "per approval-hook failure-mode mitigation"
    )
