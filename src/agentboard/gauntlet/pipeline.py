from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from agentboard.config import AgentBoardConfig, LLMConfig
from agentboard.gauntlet.lock import build_locked_plan
from agentboard.gauntlet.steps.frame import run_frame
from agentboard.gauntlet.steps.scope import run_scope
from agentboard.gauntlet.steps.arch import run_arch
from agentboard.gauntlet.steps.challenge import run_challenge
from agentboard.gauntlet.steps.decide import run_decide
from agentboard.llm.client import BudgetTracker, LLMClient
from agentboard.models import LockedPlan
from agentboard.storage.file_store import FileStore


@dataclass
class GauntletResult:
    locked_plan: LockedPlan
    frame: str = ""
    scope: str = ""
    arch: str = ""
    challenge: str = ""
    decide_raw: str = ""
    budget: BudgetTracker | None = None
    borderline_decisions: list[dict] = field(default_factory=list)


def run_gauntlet(
    goal_id: str,
    goal_description: str,
    store: FileStore,
    config: AgentBoardConfig | None = None,
    console: Console | None = None,
    on_borderline: Callable[[list[dict]], dict] | None = None,
    learnings: str = "",
    client: LLMClient | None = None,
) -> GauntletResult:
    """Run the 5-step Planning Gauntlet for a goal.

    on_borderline: called with borderline_decisions list, returns dict of answers.
    If None, uses recommendations automatically.
    client: inject a pre-built LLMClient (useful for testing with mocks).
    """
    config = config or AgentBoardConfig()
    console = console or Console()
    if client is None:
        client = LLMClient(config=config.llm)

    budget = BudgetTracker(
        goal_id=goal_id,
        token_ceiling=config.llm.max_tokens * 20,
    )

    steps = ["Frame", "Scope", "Architecture", "Challenge", "Decide"]
    outputs: dict[str, str] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:

        # Step 1: Frame
        task = progress.add_task("[cyan]Step 1/5: Frame — defining the problem...", total=None)
        frame_text, r = run_frame(client, goal_description, learnings)
        budget.record(r, "frame")
        outputs["frame"] = frame_text
        store.save_gauntlet_step(goal_id, "frame", frame_text)
        progress.update(task, description=f"[green]✓ Frame ({r.input_tokens}→{r.output_tokens} tokens)")
        console.print(f"  [dim]Frame:[/dim] {_first_line(frame_text)}")

        # Step 2: Scope
        task = progress.add_task("[cyan]Step 2/5: Scope — challenging ambition...", total=None)
        scope_text, r = run_scope(client, goal_description, frame_text)
        budget.record(r, "scope")
        outputs["scope"] = scope_text
        store.save_gauntlet_step(goal_id, "scope", scope_text)
        progress.update(task, description=f"[green]✓ Scope ({r.input_tokens}→{r.output_tokens} tokens)")
        console.print(f"  [dim]Scope:[/dim] {_first_line(scope_text)}")

        # Step 3: Architecture
        task = progress.add_task("[cyan]Step 3/5: Architecture — locking design...", total=None)
        arch_text, r = run_arch(client, goal_description, frame_text, scope_text)
        budget.record(r, "arch")
        outputs["arch"] = arch_text
        store.save_gauntlet_step(goal_id, "arch", arch_text)
        progress.update(task, description=f"[green]✓ Architecture ({r.input_tokens}→{r.output_tokens} tokens)")
        console.print(f"  [dim]Arch:[/dim] {_first_line(arch_text)}")

        # Step 4: Challenge
        task = progress.add_task("[cyan]Step 4/5: Challenge — adversarial review...", total=None)
        challenge_text, r = run_challenge(client, goal_description, frame_text, scope_text, arch_text)
        budget.record(r, "challenge")
        outputs["challenge"] = challenge_text
        store.save_gauntlet_step(goal_id, "challenge", challenge_text)
        progress.update(task, description=f"[green]✓ Challenge ({r.input_tokens}→{r.output_tokens} tokens)")
        console.print(f"  [dim]Challenge:[/dim] {_first_line(challenge_text)}")

        # Step 5: Decide
        task = progress.add_task("[cyan]Step 5/5: Decide — synthesizing locked plan...", total=None)
        plan_dict, r = run_decide(
            client, goal_description,
            frame_text, scope_text, arch_text, challenge_text,
        )
        budget.record(r, "decide")
        store.save_gauntlet_step(goal_id, "decide", r.text)
        progress.update(task, description=f"[green]✓ Decide ({r.input_tokens}→{r.output_tokens} tokens)")

    # Handle borderline decisions
    borderline = plan_dict.pop("borderline_decisions", [])
    if borderline and on_borderline:
        answers = on_borderline(borderline)
        plan_dict["borderline_answers"] = answers
    store.save_gauntlet_step(goal_id, "decisions", _format_decisions(borderline))

    locked_plan = build_locked_plan(goal_id, plan_dict)
    store.save_locked_plan(locked_plan)

    console.print(
        f"\n[bold green]✓ Gauntlet complete[/bold green]  "
        f"[dim]{budget.tokens_used:,} tokens | ${budget.cost_usd:.4f}[/dim]"
    )
    console.print(f"  Max iterations: [bold]{locked_plan.max_iterations}[/bold]  "
                  f"Token ceiling: [bold]{locked_plan.token_ceiling:,}[/bold]")
    console.print(f"  Checklist items: [bold]{len(locked_plan.goal_checklist)}[/bold]")

    return GauntletResult(
        locked_plan=locked_plan,
        frame=outputs["frame"],
        scope=outputs["scope"],
        arch=outputs["arch"],
        challenge=outputs["challenge"],
        decide_raw=r.text,
        budget=budget,
        borderline_decisions=borderline,
    )


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:80]
    return ""


def _format_decisions(borderline: list[dict]) -> str:
    if not borderline:
        return "No borderline decisions surfaced."
    lines = ["# Borderline Decisions\n"]
    for i, d in enumerate(borderline, 1):
        lines.append(f"## Decision {i}: {d.get('question', '')}")
        lines.append(f"- Option A: {d.get('option_a', '')}")
        lines.append(f"- Option B: {d.get('option_b', '')}")
        lines.append(f"- Recommendation: **{d.get('recommendation', '')}**\n")
    return "\n".join(lines)
