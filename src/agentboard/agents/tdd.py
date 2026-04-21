from __future__ import annotations

from pathlib import Path

from agentboard.agents.base import AgentResult, run_agent
from agentboard.llm.client import LLMClient, load_prompt
from agentboard.models import AtomicStep, LockedPlan
from agentboard.tools.base import ToolRegistry
from agentboard.tools.fs import make_fs_tools
from agentboard.tools.git import make_git_tools
from agentboard.tools.shell import make_shell_tool


def _common_system(phase_prompt: str, plan: LockedPlan, step: AtomicStep) -> str:
    guard = "\n".join(f"- {g}" for g in plan.out_of_scope_guard) or "(none)"
    return f"""{phase_prompt}

---
## Atomic Step
- id: {step.id}
- behavior: {step.behavior}
- test_file: {step.test_file}
- test_name: {step.test_name}
- impl_file: {step.impl_file}
- expected_fail_reason: {step.expected_fail_reason or '(not specified)'}

## Out-of-scope Guard (do not touch)
{guard}
"""


def _registry(project_root: Path, allowlist, timeout, forbids) -> ToolRegistry:
    r = ToolRegistry()
    make_fs_tools(project_root, r, forbids=forbids)
    make_shell_tool(project_root, r, allowlist=allowlist, timeout=timeout)
    make_git_tools(project_root, r)
    return r


def run_tdd_red(
    client: LLMClient,
    plan: LockedPlan,
    step: AtomicStep,
    project_root: Path,
    model: str | None = None,
    shell_allowlist=None,
    shell_timeout: int = 60,
) -> AgentResult:
    system = _common_system(load_prompt("loop/tdd_red"), plan, step)
    registry = _registry(project_root, shell_allowlist, shell_timeout, list(plan.out_of_scope_guard))
    user = (
        f"Write ONE failing test for: {step.behavior}\n"
        f"Test location: {step.test_file}::{step.test_name}\n"
        f"Then run it and verify it fails for the right reason."
    )
    return run_agent(client, system, user, registry, model=model, thinking=False)


def run_tdd_green(
    client: LLMClient,
    plan: LockedPlan,
    step: AtomicStep,
    red_summary: str,
    project_root: Path,
    model: str | None = None,
    shell_allowlist=None,
    shell_timeout: int = 60,
) -> AgentResult:
    system = _common_system(load_prompt("loop/tdd_green"), plan, step)
    registry = _registry(project_root, shell_allowlist, shell_timeout, list(plan.out_of_scope_guard))
    user = (
        f"## RED Summary\n{red_summary}\n\n"
        f"Write the minimal code to make the test at {step.test_file}::{step.test_name} pass. "
        f"Run the full suite after — no regressions allowed."
    )
    return run_agent(client, system, user, registry, model=model, thinking=False)


def run_tdd_refactor(
    client: LLMClient,
    plan: LockedPlan,
    step: AtomicStep,
    green_summary: str,
    project_root: Path,
    model: str | None = None,
    shell_allowlist=None,
    shell_timeout: int = 60,
    allow_skip: bool = True,
) -> AgentResult:
    system = _common_system(load_prompt("loop/tdd_refactor"), plan, step)
    registry = _registry(project_root, shell_allowlist, shell_timeout, list(plan.out_of_scope_guard))
    user = (
        f"## GREEN Summary\n{green_summary}\n\n"
        f"Consider {step.impl_file or step.test_file} for refactoring. "
        f"{'Skip is allowed if nothing qualifies.' if allow_skip else 'Clean up one concrete issue.'}"
    )
    return run_agent(client, system, user, registry, model=model, thinking=False)


# ── Status parsers ────────────────────────────────────────────────────────────

def parse_red_status(text: str) -> str:
    upper = text.upper()
    if "RED_CONFIRMED" in upper:
        return "RED_CONFIRMED"
    if "RED_FAILED_TO_FAIL" in upper:
        return "RED_FAILED_TO_FAIL"
    if "BLOCKED" in upper:
        return "BLOCKED"
    return "UNCLEAR"


def parse_green_status(text: str) -> str:
    upper = text.upper()
    if "GREEN_CONFIRMED" in upper:
        return "GREEN_CONFIRMED"
    if "REGRESSED" in upper:
        return "REGRESSED"
    if "GREEN_FAILED" in upper:
        return "GREEN_FAILED"
    return "UNCLEAR"


def parse_refactor_status(text: str) -> str:
    upper = text.upper()
    if "REFACTORED" in upper:
        return "REFACTORED"
    if "SKIPPED" in upper:
        return "SKIPPED"
    if "REGRESSED" in upper:
        return "REGRESSED"
    return "UNCLEAR"
