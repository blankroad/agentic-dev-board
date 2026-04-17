from __future__ import annotations

from pathlib import Path

from devboard.agents.base import AgentResult, run_agent
from devboard.llm.client import LLMClient, load_prompt
from devboard.models import LockedPlan
from devboard.tools.base import ToolRegistry
from devboard.tools.fs import make_fs_tools
from devboard.tools.git import make_git_tools
from devboard.tools.shell import make_shell_tool


def run_executor(
    client: LLMClient,
    plan: LockedPlan,
    iteration_plan: str,
    project_root: Path,
    model: str | None = None,
    shell_allowlist: list[str] | None = None,
    shell_timeout: int = 60,
    forbids: list[str] | None = None,
) -> AgentResult:
    system = load_prompt("loop/executor")
    guard = "\n".join(f"- {g}" for g in plan.out_of_scope_guard)
    system = f"{system}\n\n## Out-of-scope Guard\nNever touch these paths:\n{guard}"

    registry = ToolRegistry()
    make_fs_tools(project_root, registry, forbids=forbids or list(plan.out_of_scope_guard))
    make_shell_tool(project_root, registry, allowlist=shell_allowlist, timeout=shell_timeout)
    make_git_tools(project_root, registry)

    user_message = f"## Plan to Execute\n\n{iteration_plan}"

    return run_agent(
        client=client,
        system=system,
        user_message=user_message,
        registry=registry,
        model=model,
        thinking=False,
    )
