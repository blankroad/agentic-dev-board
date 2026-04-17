from __future__ import annotations

import json

from devboard.agents.base import AgentResult, run_agent
from devboard.llm.client import LLMClient, load_prompt
from devboard.tools.base import ToolRegistry


def run_systematic_debug(
    client: LLMClient,
    reviewer_feedback: str,
    execution_summary: str,
    test_output: str,
    iteration: int,
    history_summary: str = "",
    consecutive_failures: int = 1,
    model: str | None = None,
) -> tuple[dict, AgentResult]:
    """4-phase root cause analysis. Replaces ad-hoc reflect."""
    system = load_prompt("loop/systematic_debug")
    parts = [
        f"## Current iteration: {iteration}",
        f"## Consecutive failures on same symptom: {consecutive_failures}",
        f"\n## Reviewer feedback\n{reviewer_feedback}",
        f"\n## Execution summary\n{execution_summary}",
    ]
    if test_output:
        parts.append(f"\n## Test output (tail)\n```\n{test_output[-2000:]}\n```")
    if history_summary:
        parts.append(f"\n## History\n{history_summary}")
    parts.append("\nFollow the 4 phases strictly. Do not propose a fix in phase 1 or 2.")

    registry = ToolRegistry()
    result = run_agent(
        client=client,
        system=system,
        user_message="\n".join(parts),
        registry=registry,
        model=model,
        thinking=True,  # extended thinking for real RCA
    )

    parsed = _parse_rca(result.final_text)
    return parsed, result


def _parse_rca(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end])
            # Flatten for backwards-compat with reflect_json consumers
            return {
                "root_cause": data.get("root_cause", ""),
                "next_strategy": data.get("next_strategy", ""),
                "learning": data.get("learning", ""),
                "risk": data.get("phase_4_fix", {}).get("risk", "MEDIUM"),
                "risk_reason": "",
                "phases": data,
                "escalate": bool(data.get("phase_4_fix", {}).get("escalate_if_3_plus", False))
                          and data.get("phase_4_fix", {}).get("consecutive_failures", 0) >= 3,
            }
        except json.JSONDecodeError:
            pass
    return {
        "root_cause": text[:200],
        "next_strategy": text[:300],
        "learning": "",
        "risk": "MEDIUM",
        "risk_reason": "parse failure",
        "phases": {},
        "escalate": False,
    }
