"""agentboard CLI — observability and installer.

Orchestration (plan/run/approve/rethink) now lives in Claude Code Skills + MCP server.
This CLI keeps only:
  - install: copy skills/hooks/mcp config to ~/.claude or ./.claude
  - init: scaffold .agentboard/ (also callable from MCP)
  - board: Textual TUI for live observability
  - watch: tail .agentboard/runs/*.jsonl
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

from agentboard.config import get_agentboard_dir, load_config, save_config
from agentboard.models import BoardState, Goal, GoalStatus
from agentboard.storage.file_store import FileStore

app = typer.Typer(
    name="agentboard",
    help="agentic-dev-board — Skills + MCP + hooks for autonomous development",
    no_args_is_help=True,
)
goal_app = typer.Typer(help="Manage goals")
app.add_typer(goal_app, name="goal")

task_app = typer.Typer(help="Inspect tasks")
app.add_typer(task_app, name="task")

learnings_app = typer.Typer(help="Learnings library")
app.add_typer(learnings_app, name="learnings")

skills_app = typer.Typer(help="Manage skill packs (export/import)")
app.add_typer(skills_app, name="skills")

console = Console()


def _get_store(root: Optional[Path] = None) -> FileStore:
    from agentboard.config import find_agentboard_root
    r = root or find_agentboard_root() or Path.cwd()
    return FileStore(r)


# ── Install ───────────────────────────────────────────────────────────────


@app.command()
def install(
    scope: str = typer.Option("project", "--scope", "-s", help="project | global"),
    overwrite: bool = typer.Option(False, "--overwrite", "-f"),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install (useful when skills are already global)"),
    no_hooks: bool = typer.Option(False, "--no-hooks"),
    no_mcp: bool = typer.Option(False, "--no-mcp"),
    python_bin: Optional[str] = typer.Option(None, "--python"),
    target: str = typer.Option(
        "both",
        "--target",
        "-t",
        help="claude | opencode | both — which agent host to install for",
    ),
) -> None:
    """Install skills + hooks + MCP config for Claude Code and/or OpenCode.

    - scope=project (default): writes to <proj>/.{claude,opencode}/skills + .mcp.json + opencode.json
    - scope=global: writes skills to ~/.claude/skills/ and/or ~/.config/opencode/skills/
    - target=both (default): install for both agents. Skills are spec-compatible; only host paths differ.
    """
    from agentboard.install import (
        emit_mcp_config,
        emit_opencode_config,
        emit_settings_hooks,
        install_all,
        install_hooks,
    )

    if target not in ("claude", "opencode", "both"):
        console.print(f"[red]invalid --target: {target!r}[/red] (valid: claude|opencode|both)")
        raise typer.Exit(1)
    targets: tuple[str, ...] = (
        ("claude", "opencode") if target == "both" else (target,)
    )

    if no_skills and scope == "project":
        # User wants just the project-level wiring (hooks + MCP), skills already global
        proj = Path.cwd().resolve()
        result = {
            "scope": "project",
            "targets": list(targets),
            "installed_skills": [],
            "installed_hooks": [],
            "mcp_config": None,
            "opencode_config": None,
            "settings": None,
        }
        if not no_hooks and "claude" in targets:
            result["installed_hooks"] = [str(p) for p in install_hooks(proj / ".claude", overwrite=overwrite)]
            result["settings"] = str(emit_settings_hooks(proj))
        if not no_mcp:
            if "claude" in targets:
                result["mcp_config"] = str(emit_mcp_config(proj, python_bin=python_bin))
            if "opencode" in targets:
                result["opencode_config"] = str(emit_opencode_config(proj, python_bin=python_bin))
    else:
        result = install_all(
            scope=scope,
            overwrite=overwrite,
            with_hooks=not no_hooks,
            with_mcp=not no_mcp,
            python_bin=python_bin,
            targets=targets,
        )
    console.print(f"[green]✓[/green] scope=[bold]{scope}[/bold] targets=[bold]{','.join(targets)}[/bold]")
    console.print(f"  Skills installed: [bold]{len(result['installed_skills'])}[/bold]")
    for p in result["installed_skills"][:3]:
        console.print(f"    [dim]{p}[/dim]")
    if len(result["installed_skills"]) > 3:
        console.print(f"    [dim]... and {len(result['installed_skills']) - 3} more[/dim]")

    if scope == "project":
        if result["installed_hooks"]:
            console.print(f"  Hooks installed: {len(result['installed_hooks'])}")
        if result["mcp_config"]:
            console.print(f"  Claude MCP:     {result['mcp_config']}")
        if result.get("opencode_config"):
            console.print(f"  OpenCode MCP:   {result['opencode_config']}")
        if result["settings"]:
            console.print(f"  Settings:       {result['settings']}")
        console.print(f"\n[dim]Next: start your agent (claude / opencode) here — skills + MCP tools auto-load.[/dim]")
    else:
        console.print(f"\n[dim]Skills available globally. For hooks + MCP, run [bold]agentboard install[/bold] in each project.[/dim]")


# ── Init ──────────────────────────────────────────────────────────────────


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project root to initialize"),
) -> None:
    """Scaffold .agentboard/ in the project root."""
    root = path.resolve()
    agentboard_dir = root / ".agentboard"

    if agentboard_dir.exists():
        console.print(f"[yellow].agentboard/ already exists at {root}[/yellow]")
        raise typer.Exit(1)

    for d in [
        agentboard_dir / "goals",
        agentboard_dir / "runs",
        agentboard_dir / "learnings",
        agentboard_dir / "retros",
    ]:
        d.mkdir(parents=True)

    store = FileStore(root)
    board = BoardState()
    store.save_board(board)

    from agentboard.config import AgentBoardConfig
    save_config(AgentBoardConfig(), root)

    gitignore = root / ".gitignore"
    ignore_entries = [
        ".agentboard/runs/",
        ".agentboard/state.json",
        ".agentboard/goals/",
    ]
    existing = gitignore.read_text() if gitignore.exists() else ""
    additions = [e for e in ignore_entries if e not in existing]
    if additions:
        with open(gitignore, "a") as f:
            f.write("\n# agentboard\n" + "\n".join(additions) + "\n")

    console.print(f"[green]✓[/green] Initialized agentboard at [bold]{root}[/bold]")
    console.print(f"  Board ID: [dim]{board.board_id}[/dim]")
    console.print(f"\nNext: [bold]agentboard install[/bold] to set up skills + hooks + MCP config")


# ── MCP server ────────────────────────────────────────────────────────────


@app.command()
def mcp() -> None:
    """Start the MCP server (stdio mode). Claude Code usually spawns this automatically via .mcp.json."""
    from agentboard.mcp_server import main
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
        console.print("[dim]No goals yet. Run: agentboard goal add \"<description>\"[/dim]")
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
def task_show(
    task_id: Optional[str] = typer.Argument(None, help="Task ID (default: latest)"),
) -> None:
    """Show task details — status, decision counts, review outcomes, iter diffs."""
    from collections import Counter
    store = _get_store()
    tid = _latest_task_id(store, None, task_id)
    if not tid:
        console.print("[red]No task found.[/red]")
        raise typer.Exit(1)

    board = store.load_board()
    goal_id = None
    task = None
    for g in board.goals:
        if tid in g.task_ids:
            goal_id = g.id
            task = store.load_task(g.id, tid)
            break
    if task is None:
        console.print(f"[red]Task not found: {tid}[/red]")
        raise typer.Exit(1)

    # Header
    console.print(f"\n[bold]{task.title}[/bold]")
    console.print(f"  task_id:    [dim]{task.id}[/dim]")
    console.print(f"  goal_id:    [dim]{goal_id}[/dim]")
    console.print(f"  status:     {_status_color(task.status.value)}")
    console.print(f"  branch:     {task.branch or '(none)'}")
    converged_str = "[green]yes[/green]" if task.converged else "[yellow]no[/yellow]"
    console.print(f"  converged:  {converged_str}")

    # Decision breakdown by phase
    entries = store.load_decisions(tid)
    if entries:
        phase_counts = Counter(e.phase for e in entries)
        console.print(f"\n[bold]Decisions[/bold]  ({len(entries)} total)")
        for phase, count in sorted(phase_counts.items()):
            color = _PHASE_COLORS.get(phase, "white")
            console.print(f"  [{color}]{phase:<13}[/{color}] × {count}")

        # Review outcomes
        review_entries = [e for e in entries if e.phase in ("review", "cso", "redteam", "approval")]
        if review_entries:
            console.print(f"\n[bold]Final Verdicts[/bold]")
            for e in review_entries:
                color = _PHASE_COLORS.get(e.phase, "white")
                console.print(f"  [{color}]{e.phase:<10}[/{color}] iter {e.iter:>2}  {e.verdict_source}")

    # Iter diffs
    changes_dir = store.root / ".agentboard" / "goals" / goal_id / "tasks" / tid / "changes"
    if changes_dir.exists():
        diffs = sorted(changes_dir.glob("iter_*.diff"))
        if diffs:
            console.print(f"\n[bold]Iteration Diffs[/bold]  ({len(diffs)})")
            for p in diffs:
                size = p.stat().st_size
                console.print(f"  {p.stem}  [dim]{size} bytes[/dim]")

    console.print(
        f"\n[dim]more:[/dim] "
        f"[bold]agentboard decisions {tid}[/bold]  |  "
        f"[bold]agentboard reviews {tid}[/bold]  |  "
        f"[bold]agentboard diff {tid} --iter N[/bold]"
    )


def _status_color(s: str) -> str:
    color = {
        "converged": "blue", "pushed": "cyan", "blocked": "red",
        "awaiting_approval": "yellow", "in_progress": "green", "failed": "red",
    }.get(s, "white")
    return f"[{color}]{s}[/{color}]"


# ── Board TUI ─────────────────────────────────────────────────────────────


@app.command()
def board() -> None:
    """Launch the Textual TUI board (observability only)."""
    from agentboard.config import find_agentboard_root
    from agentboard.tui.app import run_tui

    root = find_agentboard_root() or Path.cwd()
    if not (root / ".agentboard").exists():
        console.print("[red]No .agentboard found. Run: agentboard init[/red]")
        raise typer.Exit(1)
    run_tui(store_root=root)


# ── Watch ─────────────────────────────────────────────────────────────────


@app.command()
def watch(
    run_id: Optional[str] = typer.Option(None, "--run", "-r"),
    last_n: int = typer.Option(20, "--last-n", "-n"),
    all_streams: bool = typer.Option(False, "--all", "-a", help="Tail runs AND decisions together"),
) -> None:
    """Tail .agentboard/runs/*.jsonl and/or decisions.jsonl files live.

    If no runs exist yet, falls back to tailing all decisions.jsonl so you
    always see live skill activity, even before the first `agentboard_start_task`.
    """
    import json
    import time
    import os

    store = _get_store()
    runs_dir = store.root / ".agentboard" / "runs"

    # Collect candidate files
    files_to_tail: list[tuple[Path, str]] = []  # (path, kind)

    if all_streams:
        # Both runs and decisions
        if runs_dir.exists():
            files_to_tail.extend((p, "run") for p in runs_dir.glob("*.jsonl"))
        for p in store.root.rglob(".agentboard/goals/*/tasks/*/decisions.jsonl"):
            files_to_tail.append((p, "decision"))
    elif run_id:
        rf = runs_dir / f"{run_id}.jsonl"
        if not rf.exists():
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)
        files_to_tail = [(rf, "run")]
    else:
        # Prefer newest run; fallback to all decisions
        run_files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) \
            if runs_dir.exists() else []
        if run_files:
            files_to_tail = [(run_files[0], "run")]
        else:
            # Fallback: all decisions across all tasks
            for p in store.root.rglob(".agentboard/goals/*/tasks/*/decisions.jsonl"):
                files_to_tail.append((p, "decision"))

    if not files_to_tail:
        console.print("[dim]Nothing to watch yet — no runs or decisions.[/dim]")
        console.print("[dim]Open Claude Code with agentboard skills installed, then retry.[/dim]")
        return

    console.print(
        f"[dim]Watching {len(files_to_tail)} file(s)... Ctrl+C to exit[/dim]\n"
    )

    # Show existing last N events across all files
    combined = []
    for path, kind in files_to_tail:
        for line in path.read_text().splitlines():
            combined.append((line, kind, path))
    # Crude tail: show last N overall
    for line, kind, path in combined[-last_n:]:
        _render_stream_event(line, kind, path.name)

    # Live tail — poll all files
    positions = {p: p.stat().st_size if p.exists() else 0 for p, _ in files_to_tail}
    kinds = {p: k for p, k in files_to_tail}
    try:
        while True:
            for p in list(positions.keys()):
                if not p.exists():
                    continue
                size = p.stat().st_size
                if size > positions[p]:
                    with open(p) as f:
                        f.seek(positions[p])
                        for line in f.read().splitlines():
                            if line.strip():
                                _render_stream_event(line, kinds[p], p.name)
                    positions[p] = size
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[dim]stopped.[/dim]")


def _render_stream_event(line: str, kind: str, fname: str) -> None:
    """Render a run event OR a decision entry in a unified stream."""
    import json
    line = line.strip()
    if not line:
        return
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        console.print(f"  [dim]{line[:120]}[/dim]")
        return

    if kind == "run":
        event = entry.get("event", "?")
        ts = entry.get("ts", "")[:19]
        state = entry.get("state", {}) or {}
        iter_n = state.get("iteration", "-") if isinstance(state, dict) else "-"
        color = _EVENT_COLORS.get(event, "white")
        console.print(f"  [dim]{ts}[/dim] [{color}][run][/{color}] [{color}]{event:<24}[/{color}] iter={iter_n}")
    else:  # decision
        ts = str(entry.get("ts", ""))[:19]
        iter_n = entry.get("iter", "-")
        phase = entry.get("phase", "?")
        verdict = entry.get("verdict_source", "")
        reason = entry.get("reasoning", "")[:60]
        color = _PHASE_COLORS.get(phase, "cyan")
        console.print(
            f"  [dim]{ts}[/dim] [{color}][decision][/{color}] iter={iter_n} "
            f"[{color}]{phase:<13}[/{color}] {verdict:<16} [dim]— {reason}[/dim]"
        )


_EVENT_COLORS = {
    "converged": "bold green",
    "blocked": "bold red",
    "iteration_complete": "cyan",
    "tdd_red_complete": "red",
    "tdd_green_complete": "green",
    "tdd_refactor_complete": "yellow",
    "tdd_complete": "bright_green",
    "plan_complete": "blue",
    "gauntlet_complete": "bright_blue",
    "review_complete": "magenta",
    "cso_complete": "bright_magenta",
    "redteam_complete": "bright_red",
    "rca_complete": "yellow",
    "run_start": "dim cyan",
    "replay_resumed": "bright_cyan",
}

_PHASE_COLORS = {
    "tdd_red": "red",
    "tdd_green": "green",
    "tdd_refactor": "yellow",
    "review": "magenta",
    "cso": "bright_magenta",
    "redteam": "bright_red",
    "reflect": "yellow",
    "iron_law": "bright_yellow",
    "approval": "bright_green",
    "plan": "blue",
}


# ── Status ────────────────────────────────────────────────────────────────


@app.command()
def status() -> None:
    """One-screen view of current board state — goals, active task, latest run."""
    import json
    store = _get_store()
    board = store.load_board()
    runs_dir = store.root / ".agentboard" / "runs"

    console.print(f"\n[bold]Board[/bold]  [dim]{board.board_id}[/dim]")

    if not board.goals:
        console.print("  [dim]No goals. Run: agentboard goal add \"<description>\"[/dim]")
        return

    active = board.get_goal(board.active_goal_id) if board.active_goal_id else None
    console.print(f"\n[bold]Goals ({len(board.goals)})[/bold]")
    for g in board.goals:
        marker = "●" if g.id == board.active_goal_id else " "
        color = {
            GoalStatus.active: "green", GoalStatus.converged: "blue",
            GoalStatus.awaiting_approval: "yellow", GoalStatus.pushed: "cyan",
            GoalStatus.blocked: "red", GoalStatus.archived: "dim",
        }.get(g.status, "white")
        console.print(f"  {marker} [{color}]{g.status.value:<17}[/{color}] {g.title[:60]}  [dim]{g.id[:20]} · {len(g.task_ids)} task(s)[/dim]")

    # Active goal detail
    if active and active.task_ids:
        console.print(f"\n[bold]Active Goal — Latest Task[/bold]")
        latest_task_id = active.task_ids[-1]
        task = store.load_task(active.id, latest_task_id)
        if task:
            console.print(f"  Title:     {task.title[:70]}")
            console.print(f"  Status:    {task.status.value}")
            console.print(f"  Converged: {task.converged}")

            decisions = store.load_decisions(latest_task_id)
            if decisions:
                console.print(f"  Decisions: {len(decisions)} logged")
                last = decisions[-1]
                console.print(f"  Last:      iter {last.iter} [{last.phase}] {last.verdict_source}")

    # Latest run
    if runs_dir.exists():
        run_files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if run_files:
            rf = run_files[0]
            lines = rf.read_text().splitlines()
            console.print(f"\n[bold]Latest Run[/bold]  [dim]{rf.stem}[/dim]  [dim]({len(lines)} events)[/dim]")
            events = []
            for line in lines:
                try:
                    events.append(json.loads(line).get("event", "?"))
                except Exception:
                    pass
            if events:
                tail = events[-5:]
                console.print(f"  Recent: {' → '.join(tail)}")
        else:
            console.print("\n[dim]No runs yet.[/dim]")


# ── Skills / Learnings export-import ──────────────────────────────────────


@skills_app.command("list")
def skills_list() -> None:
    """List installed agentboard skills (project + global)."""
    proj = Path.cwd() / ".claude" / "skills"
    glob = Path.home() / ".claude" / "skills"

    for label, d in [("project", proj), ("global", glob)]:
        if not d.exists():
            console.print(f"[dim]{label}: (not installed)[/dim]")
            continue
        skills = sorted(p.name for p in d.iterdir() if p.is_dir() and p.name.startswith("agentboard-"))
        if skills:
            console.print(f"[bold]{label}[/bold] ({d}):")
            for s in skills:
                console.print(f"  {s}")


@skills_app.command("export")
def skills_export(
    output: Path = typer.Option(Path("agentboard-skills.zip"), "--output", "-o"),
    scope: str = typer.Option("project", "--scope", help="project | global"),
) -> None:
    """Export installed skills as a zip — share with teammates or copy across machines."""
    import zipfile

    src_root = (Path.cwd() / ".claude" / "skills") if scope == "project" \
        else (Path.home() / ".claude" / "skills")
    if not src_root.exists():
        console.print(f"[red]No skills installed at {src_root}[/red]")
        raise typer.Exit(1)

    skill_dirs = [p for p in src_root.iterdir() if p.is_dir() and p.name.startswith("agentboard-")]
    if not skill_dirs:
        console.print(f"[red]No agentboard-* skills at {src_root}[/red]")
        raise typer.Exit(1)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for skill_dir in skill_dirs:
            for f in skill_dir.rglob("*"):
                if f.is_file():
                    arcname = f.relative_to(src_root)
                    zf.write(f, arcname)

    console.print(f"[green]✓ exported {len(skill_dirs)} skills → {output}[/green]")


@skills_app.command("import")
def skills_import(
    archive: Path = typer.Argument(...),
    scope: str = typer.Option("project", "--scope", help="project | global"),
    overwrite: bool = typer.Option(False, "--overwrite", "-f"),
) -> None:
    """Import a skills zip (produced by `agentboard skills export`)."""
    import zipfile
    if not archive.exists():
        console.print(f"[red]Not found: {archive}[/red]")
        raise typer.Exit(1)

    target = (Path.cwd() / ".claude" / "skills") if scope == "project" \
        else (Path.home() / ".claude" / "skills")
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
        # Top-level skill names (first path component)
        skill_names = sorted({n.split("/")[0] for n in names if "/" in n})
        if not overwrite:
            existing = {p.name for p in target.iterdir() if p.is_dir()}
            collisions = [n for n in skill_names if n in existing]
            if collisions:
                console.print(f"[yellow]! Already installed (use --overwrite to replace):[/yellow] {collisions}")
        zf.extractall(target)

    console.print(f"[green]✓ imported {len(skill_names)} skills → {target}[/green]")


@learnings_app.command("export")
def learnings_export(
    output: Path = typer.Option(Path("agentboard-learnings.zip"), "--output", "-o"),
) -> None:
    """Export project learnings as a zip."""
    import zipfile
    store = _get_store()
    src = store.root / ".agentboard" / "learnings"
    if not src.exists() or not any(src.iterdir()):
        console.print("[dim]No learnings to export.[/dim]")
        raise typer.Exit(0)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src.glob("*.md"):
            zf.write(f, f.name)
    console.print(f"[green]✓ exported → {output}[/green]")


@learnings_app.command("import")
def learnings_import(
    archive: Path = typer.Argument(...),
    overwrite: bool = typer.Option(False, "--overwrite", "-f"),
) -> None:
    """Import a learnings zip."""
    import zipfile
    store = _get_store()
    target = store.root / ".agentboard" / "learnings"
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
        if not overwrite:
            existing = {p.name for p in target.glob("*.md")}
            collisions = [n for n in names if n in existing]
            if collisions:
                console.print(f"[yellow]! Already present (use --overwrite):[/yellow] {collisions}")
        zf.extractall(target)

    console.print(f"[green]✓ imported {len(names)} learning(s) → {target}[/green]")


# ── Inspection commands (no JSON/jq needed) ──────────────────────────────


def _latest_goal_id(store: FileStore, explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    board = store.load_board()
    return board.active_goal_id or (board.goals[-1].id if board.goals else None)


def _latest_task_id(store: FileStore, goal_id: Optional[str], explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    board = store.load_board()
    gid = goal_id or board.active_goal_id
    for g in board.goals:
        if g.id == gid and g.task_ids:
            return g.task_ids[-1]
    return None


def _latest_run_path(store: FileStore, explicit: Optional[str]):
    runs_dir = store.root / ".agentboard" / "runs"
    if not runs_dir.exists():
        return None
    if explicit:
        p = runs_dir / f"{explicit}.jsonl"
        return p if p.exists() else None
    files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


@app.command()
def plan(
    goal_id: Optional[str] = typer.Argument(None, help="Goal ID (default: active)"),
    full: bool = typer.Option(False, "--full", "-f", help="Include Gauntlet artifacts"),
) -> None:
    """Show the LockedPlan for a goal (hash, checklist, atomic_steps, guards)."""
    store = _get_store()
    gid = _latest_goal_id(store, goal_id)
    if not gid:
        console.print("[red]No goal.[/red]")
        raise typer.Exit(1)

    locked = store.load_locked_plan(gid)
    if locked is None:
        console.print(f"[red]No plan for {gid}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]LockedPlan[/bold]  [dim]{gid}[/dim]")
    console.print(f"  hash:            [bold]{locked.locked_hash}[/bold]")
    console.print(f"  locked_at:       {locked.locked_at}")
    console.print(f"  scope_decision:  {locked.scope_decision}")
    console.print(f"  token_ceiling:   {locked.token_ceiling:,}")
    console.print(f"  max_iterations:  {locked.max_iterations}")

    console.print(f"\n[bold]Problem[/bold]\n  {locked.problem}")

    if locked.non_goals:
        console.print(f"\n[bold]Non-goals[/bold]")
        for ng in locked.non_goals:
            console.print(f"  - {ng.render_line()}")

    console.print(f"\n[bold]Goal Checklist[/bold] ({len(locked.goal_checklist)} items)")
    for item in locked.goal_checklist:
        console.print(f"  - {item}")

    console.print(f"\n[bold]Atomic Steps[/bold] ({len(locked.atomic_steps)})")
    for s in locked.atomic_steps:
        console.print(f"  [cyan]{s.id}[/cyan] {s.behavior}")
        console.print(f"    test: {s.test_file}::{s.test_name}   impl: {s.impl_file}")

    if locked.out_of_scope_guard:
        console.print(f"\n[bold]Out-of-scope Guard[/bold]")
        for g in locked.out_of_scope_guard:
            console.print(f"  - {g}")

    if locked.known_failure_modes:
        console.print(f"\n[bold]Known Failure Modes[/bold]")
        for m in locked.known_failure_modes:
            console.print(f"  - {m}")

    if full:
        gauntlet_dir = store.root / ".agentboard" / "goals" / gid / "phases"
        if gauntlet_dir.exists():
            console.print(f"\n[bold]Gauntlet Artifacts[/bold]")
            for f in sorted(gauntlet_dir.glob("*.md")):
                console.print(f"\n[dim]── {f.name} ──[/dim]")
                console.print(f.read_text())


@app.command()
def timeline(
    run_id: Optional[str] = typer.Option(None, "--run", "-r"),
    last_n: Optional[int] = typer.Option(None, "--last-n", "-n"),
) -> None:
    """Show chronological state transitions from a run (or the latest one)."""
    import json as _json
    store = _get_store()
    run_path = _latest_run_path(store, run_id)
    if not run_path:
        console.print("[dim]No runs yet.[/dim]")
        return

    console.print(f"\n[bold]Timeline[/bold]  [dim]{run_path.stem}[/dim]\n")
    entries = [_json.loads(l) for l in run_path.read_text().splitlines() if l.strip()]
    if last_n:
        entries = entries[-last_n:]

    for i, e in enumerate(entries, 1):
        ts = (e.get("ts") or "")[:19]
        event = e.get("event", "?")
        state = e.get("state") or {}
        iter_n = state.get("iteration", "")
        step = state.get("current_step_id", "")
        color = _EVENT_COLORS.get(event, "white")
        iter_str = f"iter={iter_n}" if iter_n else ""
        step_str = f"step={step}" if step else ""
        extra = "  ".join(filter(None, [iter_str, step_str]))
        console.print(f"  {i:3}. [dim]{ts}[/dim]  [{color}]{event:<26}[/{color}]  [dim]{extra}[/dim]")


@app.command()
def decisions(
    task_id: Optional[str] = typer.Argument(None),
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
    phase: Optional[str] = typer.Option(None, "--phase", "-p",
        help="Filter: plan, tdd_red, tdd_green, tdd_refactor, review, cso, redteam, reflect, iron_law, approval"),
    iter_n: Optional[int] = typer.Option(None, "--iter", "-i"),
    verdict: Optional[str] = typer.Option(None, "--verdict", "-v"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show full reasoning"),
) -> None:
    """Browse the decisions log (why each step happened)."""
    store = _get_store()
    tid = _latest_task_id(store, goal, task_id)
    if not tid:
        console.print("[red]No task found.[/red]")
        raise typer.Exit(1)

    entries = store.load_decisions(tid)
    if not entries:
        console.print(f"[dim]No decisions for task {tid}[/dim]")
        return

    # Filter
    filtered = entries
    if phase:
        filtered = [e for e in filtered if e.phase == phase]
    if iter_n is not None:
        filtered = [e for e in filtered if e.iter == iter_n]
    if verdict:
        filtered = [e for e in filtered if verdict.upper() in (e.verdict_source or "").upper()]

    console.print(f"\n[bold]Decisions[/bold]  [dim]{tid}[/dim]  ({len(filtered)}/{len(entries)} shown)\n")
    for e in filtered:
        color = _PHASE_COLORS.get(e.phase, "white")
        reasoning = e.reasoning if verbose else e.reasoning[:100]
        console.print(f"  iter {e.iter:>2}  [{color}]{e.phase:<13}[/{color}] {(e.verdict_source or '-'):<18} [dim]{reasoning}[/dim]")
        if verbose and e.next_strategy:
            console.print(f"           [dim]→ strategy: {e.next_strategy[:200]}[/dim]")


@app.command()
def reviews(
    task_id: Optional[str] = typer.Argument(None),
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
) -> None:
    """Show review outcomes — reviewer, CSO, red-team, approval."""
    store = _get_store()
    tid = _latest_task_id(store, goal, task_id)
    if not tid:
        console.print("[red]No task found.[/red]")
        raise typer.Exit(1)

    entries = store.load_decisions(tid)
    review_phases = ("review", "cso", "redteam", "approval", "iron_law")
    reviews = [e for e in entries if e.phase in review_phases]

    if not reviews:
        console.print("[dim]No review entries yet.[/dim]")
        return

    console.print(f"\n[bold]Reviews[/bold]  [dim]{tid}[/dim]\n")
    for e in reviews:
        color = _PHASE_COLORS.get(e.phase, "white")
        icon = {"PASS": "✓", "SECURE": "✓", "SURVIVED": "✓", "PUSHED": "↑",
                "RETRY": "↻", "VULNERABLE": "✗", "BROKEN": "✗",
                "RED_CONFIRMED": "—", "iron_law": "⚠"}.get(e.verdict_source or "", "·")
        console.print(
            f"  iter {e.iter:>2}  [{color}]{e.phase.upper():<10}[/{color}]  "
            f"{icon} {(e.verdict_source or '').ljust(12)}"
        )
        if e.reasoning:
            for line in e.reasoning.split("\n")[:3]:
                console.print(f"           [dim]{line[:90]}[/dim]")
            if len(e.reasoning.split("\n")) > 3:
                console.print(f"           [dim]... ({len(e.reasoning)} chars total)[/dim]")
        console.print()


@app.command()
def diff(
    task_id: Optional[str] = typer.Argument(None),
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
    iter_n: Optional[int] = typer.Option(None, "--iter", "-i", help="Specific iteration"),
    list_iters: bool = typer.Option(False, "--list", "-l", help="Just list available iter diffs"),
) -> None:
    """Show per-iteration diff archive."""
    store = _get_store()
    tid = _latest_task_id(store, goal, task_id)
    if not tid:
        console.print("[red]No task found.[/red]")
        raise typer.Exit(1)

    # Find changes dir
    board = store.load_board()
    gid = None
    for g in board.goals:
        if tid in g.task_ids:
            gid = g.id
            break
    if not gid:
        console.print("[red]Task's goal not found.[/red]")
        raise typer.Exit(1)

    changes_dir = store.root / ".agentboard" / "goals" / gid / "tasks" / tid / "changes"
    if not changes_dir.exists():
        console.print("[dim]No diffs saved for this task.[/dim]")
        return

    diffs = sorted(changes_dir.glob("iter_*.diff"))
    if not diffs:
        console.print("[dim]No diffs saved.[/dim]")
        return

    if list_iters or iter_n is None:
        console.print(f"\n[bold]Iteration Diffs[/bold]  [dim]{tid}[/dim]\n")
        for p in diffs:
            size = p.stat().st_size
            console.print(f"  {p.stem:<12}  {size:>6} bytes  [dim]{p}[/dim]")
        if iter_n is None and not list_iters:
            console.print(f"\n[dim]Use --iter N to view a specific iter[/dim]")
        return

    target = changes_dir / f"iter_{iter_n}.diff"
    if not target.exists():
        console.print(f"[red]No diff for iter {iter_n}[/red]")
        raise typer.Exit(1)
    console.print(f"\n[bold]iter_{iter_n}.diff[/bold]\n")
    console.print(target.read_text())


@app.command()
def activity(
    tool: Optional[str] = typer.Option(None, "--tool", "-t", help="Filter by tool (Write/Edit/Bash/Read/mcp...)"),
    failures_only: bool = typer.Option(False, "--failures", "-f", help="Show only errored calls"),
    last_n: int = typer.Option(50, "--last-n", "-n"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Filter by Claude Code session_id"),
) -> None:
    """Show the trial-and-error trail — every tool call (Write/Edit/Bash/MCP) with outcomes.

    Captured by the activity-log PostToolUse hook. Reveals what Claude actually
    did moment-by-moment, including failed pytest runs, rewrites, and retries —
    things that don't surface in decisions.jsonl (which only records phase outcomes).
    """
    import json as _json
    store = _get_store()
    log = store.root / ".agentboard" / "activity.jsonl"
    if not log.exists():
        console.print("[dim]No activity log yet. The activity-log hook must be installed.[/dim]")
        console.print("[dim]Run: agentboard install  (or re-install with --overwrite)[/dim]")
        return

    entries = []
    for line in log.read_text().splitlines():
        if line.strip():
            try:
                entries.append(_json.loads(line))
            except Exception:
                pass

    # Filter
    if tool:
        entries = [e for e in entries if tool.lower() in (e.get("tool") or "").lower()]
    if session:
        entries = [e for e in entries if (e.get("session_id") or "").startswith(session)]
    if failures_only:
        entries = [e for e in entries if e.get("is_error")]

    if not entries:
        console.print("[dim]No matching activity.[/dim]")
        return

    entries = entries[-last_n:]

    console.print(f"\n[bold]Activity[/bold]  ({len(entries)} shown)\n")
    for i, e in enumerate(entries, 1):
        ts = (e.get("ts") or "")[11:19]  # HH:MM:SS
        t = e.get("tool", "?")
        err = e.get("is_error")
        icon = "[red]✗[/red]" if err else "[green]·[/green]"

        # Pick most informative field
        detail = ""
        if "path" in e:
            detail = e["path"]
            if "wrote_bytes" in e:
                detail += f" ({e['wrote_bytes']}B)"
        elif "command" in e:
            detail = e["command"][:70]
            if "result_tail" in e:
                detail += f"  [dim]→ {e['result_tail']}[/dim]"
        elif "mcp_tool" in e:
            detail = e["mcp_tool"]
            if "event" in e:
                detail += f"  [dim]→ {e['event']}[/dim]"
            if "warnings" in e:
                detail += f"  [yellow]⚠ {len(e['warnings'])} warning(s)[/yellow]"
            if "mcp_error" in e:
                detail += f"  [red]error: {e['mcp_error'][:60]}[/red]"
        elif "exit_code" in e:
            detail = f"exit={e['exit_code']}"

        tool_color = {
            "Write": "blue", "Edit": "cyan", "Bash": "magenta",
            "Read": "dim", "MultiEdit": "cyan",
        }.get(t, "white")
        if t.startswith("mcp__") or "agentboard" in t.lower():
            tool_color = "bright_magenta"

        console.print(f"  {icon} [dim]{ts}[/dim] [{tool_color}]{t:<14}[/{tool_color}] {detail}")

    # Summary stats
    total_errors = sum(1 for e in entries if e.get("is_error"))
    if total_errors:
        console.print(f"\n[yellow]⚠ {total_errors} error(s) in shown range[/yellow]")


@app.command()
def violations(
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
) -> None:
    """Show all problems: Iron Law hits, RCA escalations, CSO VULNERABLE, red-team BROKEN."""
    store = _get_store()
    board = store.load_board()
    goals = [g for g in board.goals if (not goal or g.id == goal)]
    if not goals:
        console.print("[dim]No goals.[/dim]")
        return

    any_found = False
    for g in goals:
        for tid in g.task_ids:
            entries = store.load_decisions(tid)
            problems = []
            for e in entries:
                vs = (e.verdict_source or "").upper()
                if e.phase == "iron_law":
                    problems.append((e, "iron_law", "⚠"))
                elif "ESCALATED" in vs:
                    problems.append((e, "rca_escalated", "🚨"))
                elif "VULNERABLE" in vs:
                    problems.append((e, "cso_vulnerable", "🔓"))
                elif "BROKEN" in vs:
                    problems.append((e, "redteam_broken", "💥"))
            if problems:
                any_found = True
                console.print(f"\n[bold]{g.title[:60]}[/bold]  [dim]{tid}[/dim]")
                for e, kind, icon in problems:
                    color = {"iron_law": "yellow", "rca_escalated": "bright_red",
                             "cso_vulnerable": "red", "redteam_broken": "bright_red"}[kind]
                    console.print(f"  {icon} [{color}]iter {e.iter} {kind:<16}[/{color}] {e.reasoning[:90]}")

    if not any_found:
        console.print("[green]✓ No violations detected.[/green]")


@app.command("show-gauntlet")
def show_gauntlet(
    goal_id: Optional[str] = typer.Argument(None),
    step: Optional[str] = typer.Option(None, "--step", "-s",
        help="frame | scope | arch | challenge | decide (default: all)"),
) -> None:
    """Show Gauntlet 5-step artifacts (frame/scope/arch/challenge/decide)."""
    store = _get_store()
    gid = _latest_goal_id(store, goal_id)
    if not gid:
        console.print("[red]No goal.[/red]")
        raise typer.Exit(1)

    gauntlet_dir = store.root / ".agentboard" / "goals" / gid / "phases"
    if not gauntlet_dir.exists():
        console.print("[dim]No Gauntlet artifacts for this goal.[/dim]")
        return

    files = sorted(gauntlet_dir.glob("*.md"))
    if step:
        files = [f for f in files if f.stem == step]
        if not files:
            console.print(f"[red]No {step}.md[/red]")
            raise typer.Exit(1)

    for f in files:
        console.print(f"\n[bold]── {f.stem.upper()} ──[/bold]  [dim]{f.name}[/dim]\n")
        console.print(f.read_text())


# ── Documentation & Kanban ────────────────────────────────────────────────


@app.command()
def doc(
    goal_id: Optional[str] = typer.Argument(None, help="Goal ID (default: active)"),
    format: str = typer.Option("md", "--format", "-f", help="md | jira | confluence"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save to file"),
) -> None:
    """Generate a design/maintenance doc for a goal.

    Combines LockedPlan + Gauntlet artifacts + decision timeline + review
    verdicts + issues into a single narrative suitable for Confluence,
    JIRA ticket description, release notes, or PR body.
    """
    from agentboard.analytics.docgen import collect_doc

    store = _get_store()
    gid = _latest_goal_id(store, goal_id)
    if not gid:
        console.print("[red]No goal.[/red]")
        raise typer.Exit(1)

    if format not in ("md", "jira", "confluence"):
        console.print(f"[red]Unknown format: {format} (use md/jira/confluence)[/red]")
        raise typer.Exit(1)

    doc_obj = collect_doc(store, gid)
    content = doc_obj.render(format)

    if output:
        output.write_text(content)
        console.print(f"[green]✓ saved[/green] {output}  ({len(content)} chars, {format})")
    else:
        # Plain print so the output is clean for pipe/copy
        print(content)


@app.command()
def export(
    goal_id: str = typer.Argument(..., help="Goal id to export"),
    format: str = typer.Option("md", "--format", "-f", help="md | html | confluence"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write to file instead of stdout"),
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root (defaults to find_agentboard_root)"),
    source: str = typer.Option("plan", "--source", "-s", help="plan | report"),
) -> None:
    """Export a goal's plan.md or report.md.

    Reads .agentboard/goals/<goal_id>/<source>.md and emits it:
    - source=plan (default): render plan.md in the requested format (md/html/confluence).
    - source=report: emit the AI-synthesized report.md verbatim (already Markdown,
      no format rendering).
    Writes to stdout by default, or to --output file if provided.
    """
    import re as _re

    from agentboard.config import find_agentboard_root
    from agentboard.docs.export import render

    root = project_root or find_agentboard_root() or Path.cwd()

    # Reject goal_ids containing path separators or traversal tokens —
    # prevents directory traversal via `--goal-id ../../etc/passwd`.
    # Allow any `[A-Za-z0-9_-]+` for test-friendly short ids (e.g. g_cli).
    # (redteam g_20260421_013203_33d3ef FM#1 fix)
    _GOAL_ID_PATTERN = _re.compile(r"^[A-Za-z0-9_\-]+$")
    if not _GOAL_ID_PATTERN.match(goal_id):
        console.print(
            f"[red]invalid goal_id {goal_id!r} — must be [A-Za-z0-9_-]+ "
            f"(no path separators or dots)[/red]"
        )
        raise typer.Exit(1)

    # Constrain --output under the project root. Absolute paths outside
    # project_root are refused so export cannot be weaponised as an
    # arbitrary-file-write primitive. (redteam FM#2 fix)
    if output is not None:
        try:
            abs_output = output.resolve() if output.is_absolute() else (Path.cwd() / output).resolve()
            root_resolved = root.resolve()
            abs_output.relative_to(root_resolved)
        except ValueError:
            console.print(
                f"[red]--output {str(output)!r} resolves outside project root "
                f"{str(root)!r} — refused[/red]"
            )
            raise typer.Exit(1)

    if source == "report":
        report_path = root / ".agentboard" / "goals" / goal_id / "report.md"
        if not report_path.exists():
            console.print(
                f"[red]report.md not found for goal {goal_id} at {report_path}[/red]"
            )
            console.print(
                "[dim]Generate it by running `agentboard-synthesize-report` after "
                "approval, or ship a new goal to trigger auto-generation.[/dim]"
            )
            raise typer.Exit(1)
        try:
            rendered = report_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            console.print(f"[red]could not read report.md: {e}[/red]")
            raise typer.Exit(2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return

    if source != "plan":
        console.print(f"[red]unknown --source {source!r} (expected plan|report)[/red]")
        raise typer.Exit(1)

    plan_path = root / ".agentboard" / "goals" / goal_id / "plan.md"
    if not plan_path.exists():
        console.print(f"[red]no plan.md for goal {goal_id} at {plan_path}[/red]")
        raise typer.Exit(1)
    try:
        text = plan_path.read_text()
    except (OSError, UnicodeDecodeError) as e:
        console.print(f"[red]could not read plan.md: {e}[/red]")
        raise typer.Exit(2)
    try:
        rendered = render(text, format)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if output is not None:
        output.write_text(rendered)
    else:
        # stdout, no Rich formatting (print raw)
        print(rendered, end="")


@app.command()
def kanban(
    format: str = typer.Option("terminal", "--format", "-f", help="terminal | md | jira"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
) -> None:
    """Kanban-style board view — goals grouped by lifecycle status.

    Columns: Backlog / Active / Awaiting Approval / Converged / Pushed / Blocked / Archived.
    Each card shows task count, iteration count, retry count, last verdict, PR URL.
    """
    from agentboard.analytics.kanban import collect_board, render_terminal, render_markdown, render_jira

    store = _get_store()
    board = collect_board(store)

    if format == "terminal":
        console.print(render_terminal(board))
    elif format == "md":
        out = render_markdown(board)
        if output:
            output.write_text(out)
            console.print(f"[green]✓ saved[/green] {output}")
        else:
            print(out)
    elif format == "jira":
        out = render_jira(board)
        if output:
            output.write_text(out)
            console.print(f"[green]✓ saved[/green] {output}")
        else:
            print(out)
    else:
        console.print(f"[red]Unknown format: {format}[/red]")
        raise typer.Exit(1)


# ── Retro ─────────────────────────────────────────────────────────────────


@app.command()
def retro(
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
    last_n: Optional[int] = typer.Option(None, "--last-n", "-n"),
    save: bool = typer.Option(False, "--save", "-s"),
) -> None:
    """Generate a retrospective report."""
    from agentboard.analytics.retro import generate_retro, save_retro

    store = _get_store()
    report = generate_retro(store, goal_id=goal, last_n_goals=last_n)
    console.print(report.to_markdown())
    if save:
        path = save_retro(store, report)
        console.print(f"\n[green]✓ saved[/green] {path}")


# ── Metrics & Diagnose (Phase M) ──────────────────────────────────────────


@app.command()
def metrics(
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Per-project metrics — skill activation counts, convergence rate, failure modes."""
    from agentboard.analytics.metrics import collect_metrics
    import json as _json
    store = _get_store()
    m = collect_metrics(store)
    if json_output:
        console.print(_json.dumps(m.to_dict(), indent=2))
    else:
        console.print(m.to_markdown())


@app.command()
def diagnose() -> None:
    """Skill activation diagnostic — did agentboard skills actually fire?"""
    from agentboard.analytics.metrics import diagnose_activations
    store = _get_store()
    result = diagnose_activations(store)
    console.print(result.to_markdown())


# ── Replay (CLI shortcut for the MCP tool) ────────────────────────────────


@app.command()
def replay(
    run_id: str = typer.Argument(...),
    from_iter: int = typer.Option(..., "--from", "-f"),
    variant: str = typer.Option("", "--variant", "-v"),
    goal: Optional[str] = typer.Option(None, "--goal", "-g"),
) -> None:
    """Branch a run from iteration N. Creates a new replay_<id> run."""
    from agentboard.config import find_agentboard_root
    from agentboard.replay.replay import branch_run

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
    """Self-audit the agentboard CLI + installation."""
    from subprocess import run as sh
    import os

    console.print("[bold]agentboard self-audit[/bold]\n")

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

    from agentboard.config import find_agentboard_root
    root = find_agentboard_root()
    if root:
        console.print(f"  [green]✓[/green] .agentboard root: {root}")
        store = _get_store(root)
        board = store.load_board()
        console.print(f"    Goals: {len(board.goals)}")
        console.print(f"    Learnings: {len(store.list_learnings())}")
        runs_dir = root / ".agentboard" / "runs"
        runs = list(runs_dir.glob("*.jsonl")) if runs_dir.exists() else []
        console.print(f"    Runs: {len(runs)}")
    else:
        console.print("  [yellow]![/yellow] No .agentboard found (run: agentboard init)")

    # Skills/MCP/hooks installed?
    cwd = Path.cwd()
    skills_dir = cwd / ".claude" / "skills"
    global_skills = Path.home() / ".claude" / "skills"
    mcp_config = cwd / ".mcp.json"

    for label, p in [("project skills", skills_dir), ("global skills", global_skills), ("MCP config", mcp_config)]:
        if p.exists():
            if p.is_dir():
                count = sum(1 for d in p.iterdir() if d.is_dir() and d.name.startswith("agentboard-"))
                console.print(f"  [green]✓[/green] {label}: {count} agentboard-* skills at {p}")
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
    from agentboard.memory.learnings import load_all_learnings
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
    from agentboard.memory.learnings import search_learnings
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
    """Set a config value (e.g., `agentboard config tdd.enabled false`)."""
    from agentboard.config import AgentBoardConfig, find_agentboard_root
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

    new_cfg = AgentBoardConfig.model_validate(data)
    root = find_agentboard_root() or Path.cwd()
    save_config(new_cfg, root)
    console.print(f"[green]✓[/green] {key} = {target[last]}")


@app.command(name="rebuild-pile")
def rebuild_pile(
    gid: Optional[str] = typer.Argument(
        None,
        help="Goal ID to rebuild. Omit with --all to rebuild every goal.",
    ),
    all_goals: bool = typer.Option(
        False, "--all", help="Rebuild every goal under .agentboard/goals/"
    ),
    root: Optional[Path] = typer.Option(
        None, help="Project root (default: auto-detect via find_agentboard_root)"
    ),
) -> None:
    """Reconstruct canonical pile (runs/<rid>/...) from legacy decisions.jsonl.

    Use after upgrading to M1a-data to migrate existing goals forward.
    The rebuilt pile is readable by agentboard_get_session + agentboard_get_chapter MCP tools.
    """
    from agentboard.storage.pile_rebuild import rebuild_pile_all, rebuild_pile_for_goal

    store = _get_store(root)
    if all_goals:
        summary = rebuild_pile_all(store)
        failed = 0
        for g, s in summary["per_goal"].items():
            status = s.get("status", "?")
            n = s.get("tasks_rebuilt", 0)
            console.print(f"  [{status}] {g} — {n} task(s) rebuilt")
            if s.get("errors"):
                failed += len(s["errors"])
                for err in s["errors"]:
                    console.print(f"    [red]error:[/red] {err}")
        console.print(
            f"[bold]rebuild-pile --all:[/bold] {summary['goals_rebuilt']} goals, {failed} errors"
        )
        if failed:
            raise typer.Exit(code=1)
    else:
        if not gid:
            console.print("[red]error:[/red] gid required (or use --all)")
            raise typer.Exit(code=2)
        summary = rebuild_pile_for_goal(store, gid)
        if summary["status"] == "error":
            console.print(f"[red]error:[/red] {summary.get('reason', 'unknown')}")
            raise typer.Exit(code=1)
        console.print(
            f"[green]✓[/green] rebuilt {summary['tasks_rebuilt']} task(s) for {gid}"
        )
        for rid in summary.get("rids", []):
            console.print(f"  rid: {rid}")
        if summary.get("errors"):
            for err in summary["errors"]:
                console.print(f"  [red]error:[/red] {err}")
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
