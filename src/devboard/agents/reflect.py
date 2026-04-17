from __future__ import annotations

import json

from devboard.agents.base import AgentResult, run_agent
from devboard.llm.client import LLMClient, load_prompt
from devboard.tools.base import ToolRegistry


def run_reflect(
    client: LLMClient,
    reviewer_feedback: str,
    execution_summary: str,
    iteration: int,
    history_summary: str = "",
    model: str | None = None,
) -> tuple[dict, AgentResult]:
    system = load_prompt("loop/reflect")
    parts = [
        f"## Iteration {iteration} — RETRY/REPLAN",
        f"\n## Reviewer Feedback\n{reviewer_feedback}",
        f"\n## Execution Summary\n{execution_summary}",
    ]
    if history_summary:
        parts.append(f"\n## Previous Iterations\n{history_summary}")
    parts.append("\nOutput JSON only.")

    registry = ToolRegistry()
    result = run_agent(
        client=client,
        system=system,
        user_message="\n".join(parts),
        registry=registry,
        model=model,
        thinking=False,
    )

    reflect_json = _parse_reflect(result.final_text)
    return reflect_json, result


def _parse_reflect(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {
        "root_cause": text[:200],
        "next_strategy": text[:300],
        "learning": "",
        "risk": "MEDIUM",
        "risk_reason": "",
    }
