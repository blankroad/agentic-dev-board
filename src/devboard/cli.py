from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from devboard.config import get_devboard_dir, load_config, save_config
from devboard.models import BoardState, Goal, GoalStatus
from devboard.storage.file_store import FileStore

app = typer.Typer(
    name="devboard",
    help="Autonomous LLM-powered dev board",
    no_args_is_help=True,
)
goal_app = typer.Typer(help="Manage goals")
app.add_typer(goal_app, name="goal")

task_app = typer.Typer(help="Inspect tasks")
app.add_typer(task_app, name="task")

learnings_app = typer.Typer(help="Manage learnings library")
app.add_typer(learnings_app, name="learnings")

console = Console()


def _get_store(root: Optional[Path] = None) -> FileStore:
    from devboard.config import find_devboard_root
    r = root or find_devboard_root() or Path.cwd()
    return FileStore(r)


# ── Init ──────────────────────────────────────────────────────────────────


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project root to initialize"),
) -> None:
    """Scaffold .devboard/ in the project root."""
    root = path.resolve()
    devboard_dir = root / ".devboard"

    if devboard_dir.exists():
        console.print(f"[yellow].devboard/ already exists at {root}[/yellow]")
        raise typer.Exit(1)

    for d in [
        devboard_dir / "goals",
        devboard_dir / "runs",
        devboard_dir / "learnings",
    ]:
        d.mkdir(parents=True)

    store = FileStore(root)
    board = BoardState()
    store.save_board(board)

    config = load_config.__wrapped__(root) if hasattr(load_config, "__wrapped__") else load_config(root)  # type: ignore
    from devboard.config import DevBoardConfig
    save_config(DevBoardConfig(), root)

    gitignore = root / ".gitignore"
    ignore_entries = [
        ".devboard/runs/",
        ".devboard/state.json",
        ".devboard/goals/",
    ]
    existing = gitignore.read_text() if gitignore.exists() else ""
    additions = [e for e in ignore_entries if e not in existing]
    if additions:
        with open(gitignore, "a") as f:
            f.write("\n# devboard\n" + "\n".join(additions) + "\n")

    console.print(f"[green]✓[/green] Initialized devboard at [bold]{root}[/bold]")
    console.print(f"  Board ID: [dim]{board.board_id}[/dim]")
    console.print("  Run [bold]devboard goal add \"<description>\"[/bold] to add your first goal.")


# ── Goal commands ─────────────────────────────────────────────────────────


@goal_app.command("add")
def goal_add(
    description: str = typer.Argument(..., help="Goal description"),
    title: Optional[str] = typer.Option(None, "--title", "-t"),
) -> None:
    """Add a new goal to the board."""
    store = _get_store()
    board = store.load_board()

    goal = Goal(
        title=title or description[:80],
        description=description,
    )
    board.goals.append(goal)
    if board.active_goal_id is None:
        board.active_goal_id = goal.id

    store.save_goal(goal)
    store.save_board(board)

    console.print(f"[green]✓[/green] Goal added: [bold]{goal.id}[/bold]")
    console.print(f"  Title: {goal.title}")
    console.print(f"\nNext: [bold]devboard goal plan {goal.id}[/bold]")


@goal_app.command("list")
def goal_list() -> None:
    """List all goals."""
    store = _get_store()
    board = store.load_board()

    if not board.goals:
        console.print("[dim]No goals yet. Run: devboard goal add \"<description>\"[/dim]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=28)
    table.add_column("Title", min_width=30)
    table.add_column("Status", width=20)
    table.add_column("Tasks", width=6, justify="right")
    table.add_column("Active", width=7, justify="center")

    for g in board.goals:
        status_color = {
            GoalStatus.active: "green",
            GoalStatus.converged: "blue",
            GoalStatus.awaiting_approval: "yellow",
            GoalStatus.pushed: "cyan",
            GoalStatus.blocked: "red",
            GoalStatus.archived: "dim",
        }.get(g.status, "white")

        is_active = "●" if g.id == board.active_goal_id else ""
        table.add_row(
            g.id,
            g.title,
            f"[{status_color}]{g.status.value}[/{status_color}]",
            str(len(g.task_ids)),
            is_active,
        )

    console.print(table)


@goal_app.command("plan")
def goal_plan(
    goal_id: str = typer.Argument(..., help="Goal ID to run planning gauntlet for"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-run even if plan exists"),
) -> None:
    """Run the Planning Gauntlet for a goal (5-step intent lock-in)."""
    store = _get_store()
    board = store.load_board()
    goal = board.get_goal(goal_id)

    if goal is None:
        console.print(f"[red]Goal not found:[/red] {goal_id}")
        raise typer.Exit(1)

    existing_plan = store.load_locked_plan(goal_id)
    if existing_plan and not force:
        console.print(f"[yellow]Locked plan already exists (hash: {existing_plan.locked_hash})[/yellow]")
        console.print("Use [bold]--force[/bold] to re-run the gauntlet.")
        console.print(f"\nChecklist ({len(existing_plan.goal_checklist)} items):")
        for item in existing_plan.goal_checklist:
            console.print(f"  - [ ] {item}")
        raise typer.Exit(0)

    from devboard.config import find_devboard_root, load_config
    from devboard.gauntlet.pipeline import run_gauntlet
    from devboard.memory.learnings import load_relevant_learnings

    root = find_devboard_root() or Path.cwd()
    cfg = load_config(root)

    console.print(f"\n[bold]Planning Gauntlet[/bold] — [dim]{goal.title}[/dim]")
    console.print(f"[dim]Goal ID: {goal_id}[/dim]\n")

    learnings = load_relevant_learnings(store, goal.description)

    def on_borderline(decisions: list[dict]) -> dict:
        answers = {}
        console.print("\n[bold yellow]Borderline decisions need your input:[/bold yellow]")
        for d in decisions:
            console.print(f"\n[bold]{d['question']}[/bold]")
            console.print(f"  A) {d['option_a']}")
            console.print(f"  B) {d['option_b']}")
            console.print(f"  [dim]Recommendation: {d['recommendation']}[/dim]")
            choice = typer.prompt("Choice (A/B, or Enter for recommendation)", default=d['recommendation'])
            answers[d['question']] = choice.upper()
        return answers

    result = run_gauntlet(
        goal_id=goal_id,
        goal_description=goal.description or goal.title,
        store=store,
        config=cfg,
        console=console,
        on_borderline=on_borderline,
        learnings=learnings,
    )

    console.print(f"\n[bold]Locked Plan[/bold] saved to [dim].devboard/goals/{goal_id}/plan.md[/dim]")
    console.print(f"\nNext: [bold]devboard run --goal {goal_id}[/bold]")


# ── Task commands ─────────────────────────────────────────────────────────


@task_app.command("show")
def task_show(
    task_id: str = typer.Argument(..., help="Task ID"),
) -> None:
    """Show task details."""
    store = _get_store()
    board = store.load_board()

    task = None
    for goal in board.goals:
        if task_id in goal.task_ids:
            task = store.load_task(goal.id, task_id)
            break

    if task is None:
        console.print(f"[red]Task not found:[/red] {task_id}")
        raise typer.Exit(1)

    console.print(f"\n[bold]{task.title}[/bold] [dim]({task.id})[/dim]")
    console.print(f"Status:     [{_status_color(task.status.value)}]{task.status.value}[/]")
    console.print(f"Branch:     {task.branch or '(none)'}")
    console.print(f"Iterations: {len(task.iterations)}")
    console.print(f"Converged:  {task.converged}")

    if task.description:
        console.print(f"\n{task.description}")

    for it in task.iterations:
        console.print(f"\n[bold]Iteration {it.number}[/bold] — {it.started_at.strftime('%Y-%m-%d %H:%M')}")
        if it.plan_summary:
            console.print(f"  Plan:    {it.plan_summary}")
        if it.test_report:
            console.print(f"  Tests:   {it.test_report}")
        if it.review_verdict:
            console.print(f"  Review:  {it.review_verdict} — {it.review_notes}")


def _status_color(status: str) -> str:
    return {
        "todo": "white",
        "planning": "blue",
        "in_progress": "yellow",
        "reviewing": "magenta",
        "converged": "green",
        "awaiting_approval": "cyan",
        "pushed": "bright_green",
        "failed": "red",
        "blocked": "bright_red",
    }.get(status, "white")


# ── Run ───────────────────────────────────────────────────────────────────


@app.command()
def run(
    goal: Optional[str] = typer.Option(None, "--goal", "-g", help="Goal ID to run"),
    auto: bool = typer.Option(False, "--auto", help="Skip all confirmation prompts"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Log actions without executing"),
    no_tdd: bool = typer.Option(False, "--no-tdd", help="Bypass TDD enforcement (not recommended — logged)"),
    strict_tdd: bool = typer.Option(False, "--strict-tdd", help="Halt on Iron Law violations"),
    redteam: bool = typer.Option(False, "--redteam", help="Enable adversarial reviewer after PASS"),
    no_cso: bool = typer.Option(False, "--no-cso", help="Disable security reviewer (CSO) even on sensitive diffs"),
) -> None:
    """Start the autonomous planning + execution loop."""
    from devboard.config import find_devboard_root, load_config
    from devboard.gauntlet.pipeline import run_gauntlet
    from devboard.memory.learnings import load_relevant_learnings
    from devboard.models import Task, TaskStatus
    from devboard.orchestrator.runner import run_loop

    store = _get_store()
    board = store.load_board()
    cfg = load_config()
    root = find_devboard_root() or Path.cwd()

    # Apply CLI overrides
    if no_tdd:
        cfg.tdd.enabled = False
        console.print("[yellow]⚠ TDD disabled via --no-tdd (logged to decision history)[/yellow]")
    if strict_tdd:
        cfg.tdd.strict = True

    # Resolve goal
    goal_id = goal or board.active_goal_id
    if not goal_id:
        console.print("[red]No active goal. Run: devboard goal add \"<description>\"[/red]")
        raise typer.Exit(1)

    goal_obj = board.get_goal(goal_id)
    if goal_obj is None:
        console.print(f"[red]Goal not found:[/red] {goal_id}")
        raise typer.Exit(1)

    # Ensure locked plan exists
    locked_plan = store.load_locked_plan(goal_id)
    if locked_plan is None:
        console.print(f"[bold]No locked plan found — running Planning Gauntlet first...[/bold]")
        learnings = load_relevant_learnings(store, goal_obj.description)

        def on_borderline(decisions: list[dict]) -> dict:
            answers = {}
            for d in decisions:
                console.print(f"\n[bold]{d['question']}[/bold]")
                console.print(f"  A) {d['option_a']}  B) {d['option_b']}")
                choice = typer.prompt("Choice", default=d['recommendation'])
                answers[d['question']] = choice.upper()
            return answers

        gauntlet_result = run_gauntlet(
            goal_id=goal_id,
            goal_description=goal_obj.description or goal_obj.title,
            store=store,
            config=cfg,
            console=console,
            on_borderline=on_borderline if not auto else None,
            learnings=learnings,
        )
        locked_plan = gauntlet_result.locked_plan

    # Create task
    task = Task(
        goal_id=goal_id,
        title=goal_obj.title,
        description=goal_obj.description,
        status=TaskStatus.in_progress,
    )
    goal_obj.task_ids.append(task.id)
    store.save_task(task)
    store.save_board(board)

    if dry_run:
        console.print(f"[dim][dry-run] Would run loop for task {task.id}[/dim]")
        return

    tdd_active = cfg.tdd.enabled and bool(locked_plan.atomic_steps)
    console.print(f"\n[bold]Starting autonomous loop[/bold] — Task [dim]{task.id}[/dim]")
    console.print(f"  Max iterations: {locked_plan.max_iterations}")
    console.print(f"  Token ceiling:  {locked_plan.token_ceiling:,}")
    console.print(f"  Checklist:      {len(locked_plan.goal_checklist)} items")
    console.print(f"  Atomic steps:   {len(locked_plan.atomic_steps)}")
    console.print(f"  Mode:           {'[green]TDD (red-green-refactor)[/green]' if tdd_active else '[yellow]legacy single-shot[/yellow]'}")
    console.print(f"  Red-team:       {'[green]on[/green]' if redteam else '[dim]off[/dim]'}\n")

    loop_state = run_loop(
        goal_id=goal_id,
        task_id=task.id,
        goal_description=goal_obj.description or goal_obj.title,
        locked_plan=locked_plan,
        project_root=root,
        store=store,
        config=cfg,
        console=console,
        enable_redteam=redteam,
        enable_cso=not no_cso,
    )

    # Update task status
    task = store.load_task(goal_id, task.id)
    if task:
        task.status = TaskStatus.converged if loop_state.converged else TaskStatus.blocked
        task.converged = loop_state.converged
        store.save_task(task)

    if loop_state.converged:
        console.print(f"\n[bold green]✓ Loop converged in {loop_state.iteration} iteration(s)[/bold green]")
        console.print(f"  Cost: ${loop_state.cost_usd:.4f}  Tokens: {loop_state.tokens_used:,}")
        console.print(f"\nNext: [bold]devboard approve {task.id}[/bold]  (Phase D2)")
    else:
        console.print(f"\n[bold red]✗ Loop blocked:[/bold red] {loop_state.block_reason}")


# ── Board (TUI) ───────────────────────────────────────────────────────────


@app.command()
def board() -> None:
    """Launch the Textual TUI board."""
    from devboard.config import find_devboard_root
    from devboard.tui.app import run_tui

    root = find_devboard_root() or Path.cwd()
    if not (root / ".devboard").exists():
        console.print("[red]No .devboard found. Run: devboard init[/red]")
        raise typer.Exit(1)
    run_tui(store_root=root)


# ── Replay ────────────────────────────────────────────────────────────────


@app.command()
def replay(
    run_id: str = typer.Argument(..., help="Run ID to replay from"),
    from_iter: int = typer.Option(..., "--from", "-f", help="Branch from iteration N"),
    variant: str = typer.Option("", "--variant", "-v", help="Note describing the variant"),
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
) -> None:
    """Time-travel: branch a run from a past iteration and re-execute from there."""
    from devboard.config import find_devboard_root, load_config
    from devboard.models import Task, TaskStatus
    from devboard.orchestrator.runner import run_loop
    from devboard.replay.replay import branch_run, list_runs

    store = _get_store()
    board = store.load_board()
    root = find_devboard_root() or Path.cwd()

    # Resolve goal for locked plan
    goal_id = goal or board.active_goal_id
    if not goal_id:
        console.print("[red]Specify --goal or set an active goal.[/red]")
        raise typer.Exit(1)

    locked_plan = store.load_locked_plan(goal_id)
    if locked_plan is None:
        console.print(f"[red]No locked plan for goal {goal_id}[/red]")
        raise typer.Exit(1)

    result = branch_run(
        source_run_id=run_id,
        from_iteration=from_iter,
        store=store,
        locked_plan=locked_plan,
        variant_note=variant,
    )
    if result is None:
        console.print(f"[red]Run '{run_id}' not found or iteration {from_iter} not in checkpoints.[/red]")
        raise typer.Exit(1)

    new_run_id, initial_state = result
    console.print(f"\n[bold]Replay[/bold] — branching from iter {from_iter} of [dim]{run_id}[/dim]")
    console.print(f"  New run: [bold]{new_run_id}[/bold]")

    goal_obj = board.get_goal(goal_id)
    task = Task(
        goal_id=goal_id,
        title=f"[replay] {goal_obj.title if goal_obj else '?'}",
        description=f"Replay of {run_id} from iter {from_iter}. {variant}",
        status=TaskStatus.in_progress,
    )
    if goal_obj:
        goal_obj.task_ids.append(task.id)
    store.save_task(task)
    store.save_board(board)

    loop_state = run_loop(
        goal_id=goal_id,
        task_id=task.id,
        goal_description=initial_state.get("goal_description", ""),
        locked_plan=locked_plan,
        project_root=root,
        store=store,
        run_id=new_run_id,
        client=MagicMock() if False else None,
    )

    if loop_state.converged:
        console.print(f"[green]✓ Replay converged in {loop_state.iteration} iteration(s)[/green]")
    else:
        console.print(f"[red]✗ Replay blocked: {loop_state.block_reason}[/red]")


@app.command()
def rethink(
    goal_id: str = typer.Argument(..., help="Goal ID to re-run planning gauntlet for"),
) -> None:
    """Re-run the Planning Gauntlet for a goal (mid-goal replanning)."""
    from devboard.config import find_devboard_root, load_config
    from devboard.gauntlet.pipeline import run_gauntlet
    from devboard.memory.learnings import load_relevant_learnings

    store = _get_store()
    board = store.load_board()
    goal = board.get_goal(goal_id)
    if goal is None:
        console.print(f"[red]Goal not found:[/red] {goal_id}")
        raise typer.Exit(1)

    root = find_devboard_root() or Path.cwd()
    cfg = load_config(root)
    learnings = load_relevant_learnings(store, goal.description)

    console.print(f"\n[bold yellow]Rethink — re-running Gauntlet[/bold yellow]  [dim]{goal.title}[/dim]")
    console.print("[dim]Existing locked plan will be replaced.[/dim]\n")

    def on_borderline(decisions):
        answers = {}
        for d in decisions:
            console.print(f"\n[bold]{d['question']}[/bold]")
            console.print(f"  A) {d['option_a']}  B) {d['option_b']}")
            choice = typer.prompt("Choice", default=d['recommendation'])
            answers[d['question']] = choice.upper()
        return answers

    run_gauntlet(
        goal_id=goal_id,
        goal_description=goal.description or goal.title,
        store=store,
        config=cfg,
        console=console,
        on_borderline=on_borderline,
        learnings=learnings,
    )
    console.print(f"\n[green]✓ New locked plan saved.[/green]")


# ── Approve ───────────────────────────────────────────────────────────────


@app.command()
def approve(
    task_id: str = typer.Argument(..., help="Task ID to approve and push"),
    base_branch: str = typer.Option("main", "--base", "-b", help="Base branch for PR"),
    policy: Optional[str] = typer.Option(None, "--policy", "-p", help="squash|semantic|preserve|interactive"),
    draft: bool = typer.Option(False, "--draft", help="Open PR as draft"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't push"),
) -> None:
    """Approve a converged task and push + open a PR."""
    from devboard.config import find_devboard_root, load_config
    from devboard.orchestrator.approval import (
        ApprovalResult, POLICIES, apply_squash_policy,
        build_pr_body, get_diff_stats,
    )
    from devboard.orchestrator.push import ensure_branch, push_and_create_pr
    from devboard.models import GoalStatus, TaskStatus

    store = _get_store()
    board = store.load_board()
    root = find_devboard_root() or Path.cwd()
    cfg = load_config(root)

    # Find task + goal
    goal_id = None
    task = None
    for g in board.goals:
        if task_id in g.task_ids:
            goal_id = g.id
            task = store.load_task(g.id, task_id)
            break

    if task is None or goal_id is None:
        console.print(f"[red]Task not found:[/red] {task_id}")
        raise typer.Exit(1)

    goal_obj = board.get_goal(goal_id)
    locked_plan = store.load_locked_plan(goal_id)
    if locked_plan is None:
        console.print("[red]No locked plan found.[/red]")
        raise typer.Exit(1)

    decisions = store.load_decisions(task_id)

    # ── Show diff stats ───────────────────────────────────────────────────
    diff_stats = get_diff_stats(root)
    iterations_done = max((d.iter for d in decisions if d.phase == "review"), default=0)

    console.print(f"\n[bold]Approval Gate[/bold] — Task [dim]{task_id[:20]}[/dim]")
    console.print(f"  Goal: {goal_obj.title if goal_obj else '?'}")
    console.print(f"  Iterations completed: {iterations_done}")
    retries = sum(1 for d in decisions if d.phase == "review" and "RETRY" in d.reasoning.upper())
    console.print(f"  Retries: {retries}")

    if diff_stats:
        console.print(f"\n[dim]Diff stats:[/dim]\n{diff_stats}")
    else:
        console.print("\n[dim](no uncommitted diff)[/dim]")

    console.print(f"\n[bold]Goal Checklist[/bold]")
    for item in locked_plan.goal_checklist:
        console.print(f"  [green]✓[/green] {item}")

    # ── Key decisions ─────────────────────────────────────────────────────
    reflect_entries = [d for d in decisions if d.phase == "reflect"]
    if reflect_entries:
        console.print(f"\n[bold]Key Decisions ({len(reflect_entries)} reflections)[/bold]")
        for d in reflect_entries[-3:]:  # show last 3
            console.print(f"  Iter {d.iter}: {d.next_strategy[:80]}")

    # ── Squash policy ─────────────────────────────────────────────────────
    if policy is None:
        console.print("\n[bold]Squash policy[/bold]")
        console.print("  1) squash      — one clean commit (recommended)")
        console.print("  2) semantic    — one commit per task")
        console.print("  3) preserve    — keep all iteration commits")
        console.print("  4) interactive — manual rebase -i")
        choice = typer.prompt("Policy", default="1")
        policy = POLICIES.get(choice.strip(), "squash")

    console.print(f"\n  Policy: [bold]{policy}[/bold]")

    # ── Confirm ───────────────────────────────────────────────────────────
    if not typer.confirm("\nApprove and push?"):
        console.print("[yellow]Rejected — task remains in awaiting_approval.[/yellow]")
        raise typer.Exit(0)

    # ── Branch ────────────────────────────────────────────────────────────
    branch = task.branch or f"devboard/{goal_id[:8]}/{task_id[:8]}"

    if dry_run:
        console.print(f"\n[dim][dry-run] Would push branch '{branch}' with policy '{policy}'[/dim]")
        console.print(f"[dim][dry-run] Would open PR: {goal_obj.title if goal_obj else task_id}[/dim]")
        raise typer.Exit(0)

    # ── Apply squash policy ───────────────────────────────────────────────
    console.print(f"\n  Applying {policy} policy...")
    pr_title = goal_obj.title if goal_obj else task_id
    squash_msg = f"{pr_title}\n\n{iterations_done} iteration(s) via devboard"
    apply_squash_policy(root, branch, base_branch, policy, squash_msg)

    # ── Build PR body ─────────────────────────────────────────────────────
    pr_body = build_pr_body(
        locked_plan=locked_plan,
        decisions=decisions,
        iterations_completed=iterations_done,
        diff_stats=diff_stats,
    )

    # ── Push + PR ─────────────────────────────────────────────────────────
    console.print(f"  Pushing branch [bold]{branch}[/bold]...")
    result = push_and_create_pr(
        project_root=root,
        branch=branch,
        pr_title=pr_title,
        pr_body=pr_body,
        base_branch=base_branch,
        draft=draft,
    )

    if result.success:
        console.print(f"\n[bold green]✓ PR created:[/bold green] {result.pr_url}")

        # Update task + goal status
        task.status = TaskStatus.pushed
        store.save_task(task)
        if goal_obj:
            goal_obj.status = GoalStatus.pushed
            board.goals = [g if g.id != goal_id else goal_obj for g in board.goals]
            store.save_board(board)
    else:
        console.print(f"\n[bold red]✗ Push failed:[/bold red] {result.error}")
        raise typer.Exit(1)


# ── Learnings ─────────────────────────────────────────────────────────────


@learnings_app.command("list")
def learnings_list() -> None:
    """List learnings with tags + confidence."""
    from devboard.memory.learnings import load_all_learnings
    store = _get_store()
    learnings = load_all_learnings(store)
    if not learnings:
        console.print("[dim]No learnings yet.[/dim]")
        return
    for l in sorted(learnings, key=lambda x: -x.confidence):
        tags = f"[dim]({', '.join(l.tags)})[/dim]" if l.tags else ""
        console.print(f"  [{_confidence_color(l.confidence)}]{l.confidence:.1f}[/] {l.name} {tags} [dim]cat={l.category}[/dim]")


@learnings_app.command("search")
def learnings_search(
    query: str = typer.Argument("", help="Search query (optional if --tag/--category given)"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
) -> None:
    """Search learnings by query, tag, or category."""
    from devboard.memory.learnings import search_learnings
    store = _get_store()
    results = search_learnings(store, query, tag=tag, category=category)
    if not results:
        console.print("[dim]No matches.[/dim]")
        return
    for l in results:
        tag_str = f"[dim]({', '.join(l.tags)})[/dim]" if l.tags else ""
        console.print(f"\n[bold]{l.name}[/bold] {tag_str} [dim]conf={l.confidence:.1f}[/dim]")
        console.print(l.content[:300])


def _confidence_color(c: float) -> str:
    if c >= 0.8: return "bold green"
    if c >= 0.5: return "yellow"
    return "dim"


# ── Retro ─────────────────────────────────────────────────────────────────


@app.command()
def retro(
    goal: Optional[str] = typer.Option(None, "--goal", "-g", help="Specific goal ID"),
    last_n: Optional[int] = typer.Option(None, "--last-n", "-n", help="Last N goals"),
    save: bool = typer.Option(False, "--save", "-s", help="Save markdown to .devboard/retros/"),
) -> None:
    """Generate a retrospective report across goals + runs."""
    from devboard.analytics.retro import generate_retro, save_retro

    store = _get_store()
    report = generate_retro(store, goal_id=goal, last_n_goals=last_n)
    md = report.to_markdown()
    console.print(md)
    if save:
        path = save_retro(store, report)
        console.print(f"\n[green]✓ saved[/green] {path}")


# ── Audit (self-DX review) ────────────────────────────────────────────────


@app.command()
def audit() -> None:
    """Self-audit the devboard CLI for developer experience issues."""
    from subprocess import run as sh
    from devboard.cli import app as typer_app

    console.print("[bold]devboard self-audit[/bold]\n")

    # 1. All top-level commands have --help
    commands = [c.name for c in typer_app.registered_commands]
    sub_apps = [(t.typer_instance.info.name or "?", t) for t in typer_app.registered_groups]
    console.print(f"  Top-level commands: [bold]{len(commands)}[/bold]")
    console.print(f"  Sub-apps: [bold]{len(sub_apps)}[/bold]")

    # 2. Check each command has a docstring / help text
    missing_help = []
    for c in typer_app.registered_commands:
        help_text = (c.help or "").strip() or (c.callback.__doc__ or "").strip()
        if not help_text:
            missing_help.append(c.name)
    if missing_help:
        console.print(f"  [red]✗[/red] Missing help: {missing_help}")
    else:
        console.print(f"  [green]✓[/green] All commands have help text")

    # 3. State: .devboard/ exists?
    from devboard.config import find_devboard_root
    root = find_devboard_root()
    if root:
        console.print(f"  [green]✓[/green] .devboard root: {root}")
        store = _get_store(root)
        board = store.load_board()
        console.print(f"  Goals: {len(board.goals)}")
        console.print(f"  Learnings: {len(store.list_learnings())}")
        runs_dir = root / ".devboard" / "runs"
        runs = list(runs_dir.glob("*.jsonl")) if runs_dir.exists() else []
        console.print(f"  Runs: {len(runs)}")
    else:
        console.print("  [yellow]![/yellow] No .devboard directory found (not initialized)")

    # 4. ANTHROPIC_API_KEY present?
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        console.print("  [green]✓[/green] ANTHROPIC_API_KEY set")
    else:
        console.print("  [red]✗[/red] ANTHROPIC_API_KEY not set — devboard run will fail")

    # 5. Tool versions
    for tool in ["git", "pytest", "gh"]:
        try:
            r = sh([tool, "--version"], capture_output=True, text=True, timeout=5)
            version = r.stdout.splitlines()[0] if r.stdout else "(no output)"
            console.print(f"  [green]✓[/green] {tool}: {version}")
        except Exception:
            console.print(f"  [yellow]![/yellow] {tool}: not found")


# ── Config ────────────────────────────────────────────────────────────────


@app.command()
def config(
    key: str = typer.Argument(...),
    value: str = typer.Argument(...),
) -> None:
    """Set a config value."""
    from devboard.config import DevBoardConfig
    store = _get_store()
    cfg = load_config()
    data = cfg.model_dump()

    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        if part not in target:
            console.print(f"[red]Unknown config key:[/red] {key}")
            raise typer.Exit(1)
        target = target[part]

    last = parts[-1]
    if last not in target:
        console.print(f"[red]Unknown config key:[/red] {key}")
        raise typer.Exit(1)

    existing = target[last]
    if isinstance(existing, bool):
        target[last] = value.lower() in ("true", "1", "yes")
    elif isinstance(existing, int):
        target[last] = int(value)
    else:
        target[last] = value

    new_cfg = DevBoardConfig.model_validate(data)
    from devboard.config import find_devboard_root
    root = find_devboard_root() or Path.cwd()
    save_config(new_cfg, root)
    console.print(f"[green]✓[/green] {key} = {target[last]}")


if __name__ == "__main__":
    app()
