from __future__ import annotations

from agentboard.agents.base import AgentResult, run_agent
from agentboard.llm.client import LLMClient, load_prompt
from agentboard.models import LockedPlan
from agentboard.tools.base import ToolRegistry


def run_redteam(
    client: LLMClient,
    plan: LockedPlan,
    execution_summary: str,
    test_output: str,
    diff: str = "",
    model: str | None = None,
) -> tuple[bool, AgentResult]:
    """Adversarial review after PASS verdict. Returns (survived, result).

    survived=True means the implementation withstood attack.
    survived=False means a breaking scenario was found — loop should RETRY.
    """
    system = load_prompt("loop/redteam")
    checklist = "\n".join(f"- {item}" for item in plan.goal_checklist)
    system = f"{system}\n\n## Goal Checklist (what must hold)\n{checklist}"

    parts = [
        "## Execution Summary",
        execution_summary,
        "\n## Test Output",
        f"```\n{test_output or '(none)'}\n```",
    ]
    if diff:
        parts += ["\n## Diff", f"```diff\n{diff[:3000]}\n```"]
    parts.append("\nFind at least 3 breaking scenarios. Be specific and ruthless.")

    registry = ToolRegistry()
    result = run_agent(
        client=client,
        system=system,
        user_message="\n".join(parts),
        registry=registry,
        model=model,
        thinking=False,
    )

    survived = _parse_survived(result.final_text)
    return survived, result


def _parse_survived(text: str) -> bool:
    upper = text.upper()
    # Look for explicit SURVIVED or BROKEN verdict
    if "VERDICT: SURVIVED" in upper or "**SURVIVED**" in upper:
        return True
    if "VERDICT: BROKEN" in upper or "**BROKEN**" in upper:
        return False
    # Heuristic: if CRITICAL issues mentioned, consider broken
    if "CRITICAL" in upper and ("BROKEN" in upper or "FAIL" in upper):
        return False
    return True
