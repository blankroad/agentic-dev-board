from __future__ import annotations

from devboard.agents.base import AgentResult, run_agent
from devboard.llm.client import LLMClient, load_prompt
from devboard.models import LockedPlan


def _build_system(plan: LockedPlan) -> str:
    prompt = load_prompt("loop/planner")
    checklist = "\n".join(f"- [ ] {item}" for item in plan.goal_checklist)
    guard = "\n".join(f"- {g}" for g in plan.out_of_scope_guard)
    return f"""{prompt}

---
## Locked Plan

**Problem**: {plan.problem}

**Architecture**: {plan.architecture}

**Goal Checklist**:
{checklist}

**Out-of-scope Guard** (never touch these):
{guard}

**Token ceiling**: {plan.token_ceiling:,}
**Max iterations**: {plan.max_iterations}
"""


def run_planner(
    client: LLMClient,
    plan: LockedPlan,
    iteration: int,
    previous_verdict: str = "",
    previous_strategy: str = "",
    model: str | None = None,
) -> AgentResult:
    system = _build_system(plan)

    context_parts = [f"## Current Iteration: {iteration}"]
    if previous_verdict:
        context_parts.append(f"\n## Previous Reviewer Verdict\n{previous_verdict}")
    if previous_strategy:
        context_parts.append(f"\n## Strategy from Reflect\n{previous_strategy}")
    context_parts.append("\nPlease produce the implementation plan for this iteration.")

    from devboard.tools.base import ToolRegistry
    registry = ToolRegistry()  # Planner doesn't use tools — text-only

    return run_agent(
        client=client,
        system=system,
        user_message="\n".join(context_parts),
        registry=registry,
        model=model,
        thinking=True,
    )
