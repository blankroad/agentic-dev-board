from __future__ import annotations

import uuid
from pathlib import Path

from rich.console import Console

from agentboard.agents.router import route
from agentboard.config import AgentBoardConfig
from agentboard.llm.client import BudgetTracker, LLMClient
from agentboard.models import LockedPlan
from agentboard.orchestrator.checkpointer import Checkpointer
from agentboard.orchestrator.graph import build_graph
from agentboard.orchestrator.interrupt import HintQueue
from agentboard.orchestrator.state import LoopState
from agentboard.storage.file_store import FileStore


def run_loop(
    goal_id: str,
    task_id: str,
    goal_description: str,
    locked_plan: LockedPlan,
    project_root: Path,
    store: FileStore,
    config: AgentBoardConfig | None = None,
    console: Console | None = None,
    client: LLMClient | None = None,
    run_id: str | None = None,
    resume: bool = False,
    hint_queue: HintQueue | None = None,
    enable_redteam: bool = False,
    enable_cso: bool = True,
) -> LoopState:
    """Run the plan→impl→test→review cyclic loop via LangGraph until convergence."""
    config = config or AgentBoardConfig()
    console = console or Console()
    if client is None:
        client = LLMClient(config=config.llm)

    run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"
    run_path = store.root / ".devboard" / "runs" / f"{run_id}.jsonl"
    checkpointer = Checkpointer(run_path)

    budget = BudgetTracker(
        goal_id=goal_id,
        token_ceiling=locked_plan.token_ceiling,
    )

    # Resume from checkpoint if requested
    start_iteration = 1
    initial_history: list[dict] = []
    initial_reflect: dict = {}
    if resume:
        resume_point = checkpointer.find_resume_point()
        if resume_point:
            start_iteration, prev_state = resume_point
            start_iteration += 1  # start from next iteration
            initial_history = prev_state.get("history", [])
            initial_reflect = prev_state.get("reflect_json", {})
            console.print(f"[dim]Resuming from iteration {start_iteration}[/dim]")

    graph = build_graph(
        locked_plan=locked_plan,
        store=store,
        budget=budget,
        checkpointer=checkpointer,
        client=client,
        config=config,
        console=console,
        hint_queue=hint_queue,
        enable_redteam=enable_redteam,
        enable_cso=enable_cso,
    )
    compiled = graph.compile()

    initial_state = {
        "goal_id": goal_id,
        "task_id": task_id,
        "goal_description": goal_description,
        "project_root": str(project_root),
        "max_iterations": locked_plan.max_iterations,
        "iteration": start_iteration,
        "plan_text": "",
        "execution_summary": "",
        "test_output": "",
        "diff": "",
        "prev_diff": "",
        "verdict": "",
        "reviewer_feedback": "",
        "redteam_feedback": "",
        "reflect_json": initial_reflect,
        "converged": False,
        "blocked": False,
        "block_reason": "",
        "tokens_used": 0,
        "cost_usd": 0.0,
        "history": initial_history,
        "pending_hints": [],
        # Phase G TDD state
        "current_step_id": "",
        "red_summary": "",
        "green_summary": "",
        "refactor_summary": "",
        "tdd_status": "",
        "verification_report": "",
        "consecutive_failures": 0,
        "cso_feedback": "",
    }

    checkpointer.save("run_start", {"run_id": run_id, "goal_id": goal_id, "task_id": task_id})

    final_state = compiled.invoke(initial_state)

    return LoopState(
        goal_id=goal_id,
        task_id=task_id,
        goal_description=goal_description,
        locked_plan_hash=locked_plan.locked_hash,
        project_root=str(project_root),
        iteration=final_state.get("iteration", 1),
        converged=final_state.get("converged", False),
        blocked=final_state.get("blocked", False),
        block_reason=final_state.get("block_reason", ""),
        tokens_used=budget.tokens_used,
        cost_usd=budget.cost_usd,
    )
