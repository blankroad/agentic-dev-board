from __future__ import annotations

from devboard.agents.base import AgentResult, run_agent
from devboard.llm.client import LLMClient, load_prompt
from devboard.models import LockedPlan, ReviewVerdict
from devboard.tools.base import ToolRegistry


def parse_verdict(text: str) -> ReviewVerdict:
    upper = text.upper()
    if "VERDICT: PASS" in upper or "**PASS**" in upper or "VERDICT:**PASS**" in upper:
        return ReviewVerdict.pass_
    if "VERDICT: REPLAN" in upper or "**REPLAN**" in upper:
        return ReviewVerdict.replan
    return ReviewVerdict.retry


def run_reviewer(
    client: LLMClient,
    plan: LockedPlan,
    execution_summary: str,
    test_output: str,
    diff: str = "",
    model: str | None = None,
) -> tuple[ReviewVerdict, AgentResult]:
    system = load_prompt("loop/reviewer")
    checklist = "\n".join(f"- [ ] {item}" for item in plan.goal_checklist)
    system = f"{system}\n\n## Goal Checklist\n{checklist}"

    parts = ["## Execution Summary", execution_summary]
    if test_output:
        parts += ["\n## Test Output", f"```\n{test_output}\n```"]
    if diff:
        parts += ["\n## Diff", f"```diff\n{diff}\n```"]
    parts.append("\nPlease review and issue your verdict.")

    registry = ToolRegistry()  # Reviewer is text-only

    result = run_agent(
        client=client,
        system=system,
        user_message="\n".join(parts),
        registry=registry,
        model=model,
        thinking=True,
    )

    verdict = parse_verdict(result.final_text)
    return verdict, result


def is_pass(verdict: ReviewVerdict) -> bool:
    return verdict == ReviewVerdict.pass_
