"""devboard CLI — observability and installer.

Orchestration (plan/run/approve/rethink) now lives in Claude Code Skills + MCP server.
This CLI keeps only:
  - install: copy skills/hooks/mcp config to ~/.claude or ./.claude
  - init: scaffold .devboard/ (also callable from MCP)
  - board: Textual TUI for live observability
  - watch: tail .devboard/runs/*.jsonl
  - retro: standalone retrospective report (no LLM)
  - audit: self-DX checks
  - replay: time-travel CLI shortcut (same logic as MCP tool)
  - learnings: list/search
  - goal: list/add goals
  - task: show task detail
  - mcp: start MCP server (stdio) — Claude Code usually spawns this automatically
  - config: set config values
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from devboard.config import get_devboard_dir, load_config, save_config
from devboard.models import BoardState, Goal, GoalStatus
from devboard.storage.file_store import FileStore

app = typer.Typer(
    name="devboard",
    help="agentic-dev-board — Skills + MCP + hooks for autonomous development",
    no_args_is_help=True,
)
goal_app = typer.Typer(help="Manage goals")
app.add_typer(goal_app, name="goal")

task_app = typer.Typer(help="Inspect tasks")
app.add_typer(task_app, name="task")

learnings_app = typer.Typer(help="Learnings library")
app.add_typer(learnings_app, name="learnings")

console = Console()


def _get_store(root: Optional[Path] = None) -> FileStore:
    from devboard.config import find_devboard_root
    r = root or find_devboard_root() or Path.cwd()
    return FileStore(r)


# ── Install ───────────────────────────────────────────────────────────────


@app.command()
def install(
    scope: str = typer.Option("project", "--scope", "-s", help="project | global"),
    overwrite: bool = typer.Option(False, "--overwrite", "-f"),
    no_hooks: bool = typer.Option(False, "--no-hooks"),
    no_mcp: bool = typer.Option(False, "--no-mcp"),
    python_bin: Optional[str] = typer.Option(None, "--python"),
) -> None:
    """Install skills + hooks + MCP config.

    - scope=project (default): writes to ./.claude/{skills,hooks,settings.json} + ./.mcp.json
    - scope=global: writes skills to ~/.claude/skills/ only (hooks/MCP are per-project in Claude Code)
    """
    from devboard.install import install_all

    result = install_all(
        scope=scope,
        overwrite=overwrite,
        with_hooks=not no_hooks,
        with_mcp=not no_mcp,
        python_bin=python_bin,
    )
    console.print(f"[green]✓[/green] scope=[bold]{scope}[/bold]")
    console.print(f"  Skills installed: [bold]{len(result['installed_skills'])}[/bold]")
    for p in result["installed_skills"][:3]:
        console.print(f"    [dim]{p}[/dim]")
    if len(result["installed_skills"]) > 3:
        console.print(f"    [dim]... and {len(result['installed_skills']) - 3} more[/dim]")

    if scope == "project":
        if result["installed_hooks"]:
            console.print(f"  Hooks installed: {len(result['installed_hooks'])}")
        if result["mcp_config"]:
            console.print(f"  MCP config:     {result['mcp_config']}")
        if result["settings"]:
            console.print(f"  Settings:       {result['settings']}")
        console.print(f"\n[dim]Next: start Claude Code in this directory. Skills and MCP tools are auto-loaded.[/dim]")
    else:
        console.print(f"\n[dim]Skills available globally. For hooks + MCP, run [bold]devboard install[/bold] in each project.[/dim]")


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
        devboard_dir / "retros",
    ]:
        d.mkdir(parents=True)

    store = FileStore(root)
    board = BoardState()
    store.save_board(board)

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
    console.print(f"\nNext: [bold]devboard install[/bold] to set up skills + hooks + MCP config")


# ── MCP server ────────────────────────────────────────────────────────────


@app.command()
def mcp() -> None:
    """Start the MCP server (stdio mode). Claude Code usually spawns this automatically via .mcp.json."""
    from devboard.mcp_server import main
    main()


# ── Goals ─────────────────────────────────────────────────────────────────


@goal_app.command("add")
def goal_add(
    description: str = typer.Argument(..., help="Goal description"),
    title: Optional[str] = typer.Option(None, "--title", "-t"),
) -> None:
    """Add a new goal."""
    store = _get_store()
    board = store.load_board()
    goal = Goal(title=title or description[:80], description=description)
    board.goals.append(goal)
    if board.active_goal_id is None:
        board.active_goal_id = goal.id
    store.save_goal(goal)
    store.save_board(board)
    console.print(f"[green]✓[/green] Goal added: [bold]{goal.id}[/bold]")
    console.print(f"\nNext: open Claude Code and ask it to plan this goal — skills auto-activate.")


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
            g.id, g.title,
            f"[{status_color}]{g.status.value}[/{status_color}]",
            str(len(g.task_ids)), is_active,
        )
    console.print(table)


# ── Tasks ─────────────────────────────────────────────────────────────────


@task_app.command("show")
def task_show(task_id: str = typer.Argument(...)) -> None:
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
    console.print(f"Status:     {task.status.value}")
    console.print(f"Branch:     {task.branch or '(none)'}")
    console.print(f"Iterations: {len(task.iterations)}")
    console.print(f"Converged:  {task.converged}")

    entries = store.load_decisions(task.id)
    if entries:
        console.print(f"\n[bold]Decisions ({len(entries)})[/bold]")
        for e in entries[-10:]:
            console.print(f"  iter {e.iter} [{e.phase}] — {e.reasoning[:80]}")


# ── Board TUI ─────────────────────────────────────────────────────────────


@app.command()
def board() -> None:
    """Launch the Textual TUI board (observability only)."""
    from devboard.config import find_devboard_root
    from devboard.tui.app import run_tui

    root = find_devboard_root() or Path.cwd()
    if not (root / ".devboard").exists():
        console.print("[red]No .devboard found. Run: devboard init[/red]")
        raise typer.Exit(1)
    run_tui(store_root=root)


# ── Watch ─────────────────────────────────────────────────────────────────


@app.command()
def watch(
    run_id: Optional[str] = typer.Option(None, "--run", "-r"),
    last_n: int = typer.Option(20, "--last-n", "-n"),
) -> None:
    """Tail the latest run's state transitions from .devboard/runs/*.jsonl."""
    import json
    import time

    store = _get_store()
    runs_dir = store.root / ".devboard" / "runs"
    if not runs_dir.exists():
        console.print("[red]No runs directory found.[/red]")
        raise typer.Exit(1)

    if run_id:
        run_file = runs_dir / f"{run_id}.jsonl"
    else:
        files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            console.print("[dim]No runs yet.[/dim]")
            return
        run_file = files[0]

    if not run_file.exists():
        console.print(f"[red]Run file not found:[/red] {run_file}")
        raise typer.Exit(1)

    console.print(f"[dim]Watching {run_file.name}... Ctrl+C to exit[/dim]\n")

    # Show existing last N events
    lines = run_file.read_text().splitlines()
    for line in lines[-last_n:]:
        _render_event(line)

    # Tail
    try:
        with open(run_file) as f:
            f.seek(0, 2)  # to end
            while True:
                line = f.readline()
                if line:
                    _render_event(line)
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[dim]stopped.[/dim]")


def _render_event(line: str) -> None:
    import json
    line = line.strip()
    if not line:
        return
    try:
        entry = json.loads(line)
        event = entry.get("event", "?")
        ts = entry.get("ts", "")[:19]
        state = entry.get("state", {})
        iter_n = state.get("iteration", "-") if isinstance(state, dict) else "-"
        color = {
            "converged": "bold green",
            "blocked": "bold red",
            "iteration_complete": "cyan",
            "tdd_red_complete": "red",
            "tdd_green_complete": "green",
            "plan_complete": "blue",
            "review_complete": "magenta",
        }.get(event, "white")
        console.print(f"  [{color}]{event:<24}[/{color}] iter={iter_n}  [dim]{ts}[/dim]")
    except Exception:
        console.print(f"  [dim]{line[:120]}[/dim]")


# ── Retro ─────────────────────────────────────────────────────────────────


@app.command()
def retro(
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
    last_n: Optional[int] = typer.Option(None, "--last-n", "-n"),
    save: bool = typer.Option(False, "--save", "-s"),
) -> None:
    """Generate a retrospective report."""
    from devboard.analytics.retro import generate_retro, save_retro

    store = _get_store()
    report = generate_retro(store, goal_id=goal, last_n_goals=last_n)
    console.print(report.to_markdown())
    if save:
        path = save_retro(store, report)
        console.print(f"\n[green]✓ saved[/green] {path}")


# ── Replay (CLI shortcut for the MCP tool) ────────────────────────────────


@app.command()
def replay(
    run_id: str = typer.Argument(...),
    from_iter: int = typer.Option(..., "--from", "-f"),
    variant: str = typer.Option("", "--variant", "-v"),
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
) -> None:
    """Branch a run from iteration N. Creates a new replay_<id> run."""
    from devboard.config import find_devboard_root
    from devboard.replay.replay import branch_run

    store = _get_store()
    board = store.load_board()
    goal_id = goal or board.active_goal_id
    if not goal_id:
        console.print("[red]Specify --goal[/red]")
        raise typer.Exit(1)
    plan = store.load_locked_plan(goal_id)
    if plan is None:
        console.print(f"[red]No locked plan for goal {goal_id}[/red]")
        raise typer.Exit(1)

    result = branch_run(run_id, from_iter, store, plan, variant_note=variant)
    if result is None:
        console.print(f"[red]Run {run_id} / iter {from_iter} not found[/red]")
        raise typer.Exit(1)

    new_run_id, _ = result
    console.print(f"[green]✓[/green] Branched: [bold]{new_run_id}[/bold]")
    console.print(f"  Open Claude Code and ask to 'resume replay {new_run_id}'")


# ── Audit ─────────────────────────────────────────────────────────────────


@app.command()
def audit() -> None:
    """Self-audit the devboard CLI + installation."""
    from subprocess import run as sh
    import os

    console.print("[bold]devboard self-audit[/bold]\n")

    commands = [c.name for c in app.registered_commands]
    console.print(f"  Top-level commands: [bold]{len(commands)}[/bold]")

    missing_help = []
    for c in app.registered_commands:
        help_text = (c.help or "").strip() or (c.callback.__doc__ or "").strip()
        if not help_text:
            missing_help.append(c.name)
    if missing_help:
        console.print(f"  [red]✗[/red] Missing help: {missing_help}")
    else:
        console.print(f"  [green]✓[/green] All commands have help text")

    from devboard.config import find_devboard_root
    root = find_devboard_root()
    if root:
        console.print(f"  [green]✓[/green] .devboard root: {root}")
        store = _get_store(root)
        board = store.load_board()
        console.print(f"    Goals: {len(board.goals)}")
        console.print(f"    Learnings: {len(store.list_learnings())}")
        runs_dir = root / ".devboard" / "runs"
        runs = list(runs_dir.glob("*.jsonl")) if runs_dir.exists() else []
        console.print(f"    Runs: {len(runs)}")
    else:
        console.print("  [yellow]![/yellow] No .devboard found (run: devboard init)")

    # Skills/MCP/hooks installed?
    cwd = Path.cwd()
    skills_dir = cwd / ".claude" / "skills"
    global_skills = Path.home() / ".claude" / "skills"
    mcp_config = cwd / ".mcp.json"

    for label, p in [("project skills", skills_dir), ("global skills", global_skills), ("MCP config", mcp_config)]:
        if p.exists():
            if p.is_dir():
                count = sum(1 for d in p.iterdir() if d.is_dir() and d.name.startswith("devboard-"))
                console.print(f"  [green]✓[/green] {label}: {count} devboard-* skills at {p}")
            else:
                console.print(f"  [green]✓[/green] {label}: {p}")
        else:
            console.print(f"  [yellow]![/yellow] {label}: not installed")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("  [yellow]![/yellow] ANTHROPIC_API_KEY not set (not needed if using Claude Code subscription)")

    for tool in ["git", "pytest", "gh", "claude"]:
        try:
            r = sh([tool, "--version"], capture_output=True, text=True, timeout=5)
            version = r.stdout.splitlines()[0] if r.stdout else "(no output)"
            console.print(f"  [green]✓[/green] {tool}: {version}")
        except Exception:
            console.print(f"  [yellow]![/yellow] {tool}: not found")


# ── Learnings ─────────────────────────────────────────────────────────────


@learnings_app.command("list")
def learnings_list() -> None:
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
    query: str = typer.Argument(""),
    tag: Optional[str] = typer.Option(None, "--tag", "-t"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
) -> None:
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


# ── Config ────────────────────────────────────────────────────────────────


@app.command()
def config(
    key: str = typer.Argument(...),
    value: str = typer.Argument(...),
) -> None:
    """Set a config value (e.g., `devboard config tdd.enabled false`)."""
    from devboard.config import DevBoardConfig, find_devboard_root
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
    root = find_devboard_root() or Path.cwd()
    save_config(new_cfg, root)
    console.print(f"[green]✓[/green] {key} = {target[last]}")


if __name__ == "__main__":
    app()
