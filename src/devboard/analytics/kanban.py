"""Kanban board view — groups goals by lifecycle status into columns.

Status lifecycle:
  backlog → active → (testing/reviewing implicit) → awaiting_approval → pushed
  (or) → blocked → archived

Rendered as terminal table (via rich) or markdown (for pasting into Confluence/JIRA).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from devboard.models import Goal, GoalStatus
from devboard.storage.file_store import FileStore


_COLUMN_ORDER: list[tuple[str, list[GoalStatus]]] = [
    ("Backlog", []),  # no status maps here by default; could be populated by gauntlet-less goals
    ("Active", [GoalStatus.active]),
    ("Awaiting Approval", [GoalStatus.awaiting_approval]),
    ("Converged", [GoalStatus.converged]),
    ("Pushed", [GoalStatus.pushed]),
    ("Blocked", [GoalStatus.blocked]),
    ("Archived", [GoalStatus.archived]),
]


@dataclass
class KanbanCard:
    goal: Goal
    task_count: int = 0
    iteration_count: int = 0
    retry_count: int = 0
    has_plan: bool = False
    last_verdict: str = ""
    pr_url: str = ""


@dataclass
class KanbanBoard:
    columns: dict[str, list[KanbanCard]] = field(default_factory=dict)
    total_goals: int = 0


def collect_board(store: FileStore) -> KanbanBoard:
    board_state = store.load_board()
    board = KanbanBoard(total_goals=len(board_state.goals))
    for col_name, _ in _COLUMN_ORDER:
        board.columns[col_name] = []

    for goal in board_state.goals:
        card = KanbanCard(goal=goal, task_count=len(goal.task_ids))
        card.has_plan = store.load_locked_plan(goal.id) is not None

        # Aggregate task stats
        for tid in goal.task_ids:
            decs = store.load_decisions(tid)
            iters = {d.iter for d in decs}
            card.iteration_count = max(card.iteration_count, len(iters))
            for d in decs:
                if d.phase == "review" and "RETRY" in (d.verdict_source or ""):
                    card.retry_count += 1
                if d.phase == "approval" and "https://" in d.reasoning:
                    import re
                    m = re.search(r"https?://\S+", d.reasoning)
                    if m:
                        card.pr_url = m.group(0).rstrip(".,)")
            # last verdict
            review_decs = [d for d in decs if d.phase in ("review", "redteam", "approval")]
            if review_decs:
                card.last_verdict = review_decs[-1].verdict_source or ""

        # Slot into column
        placed = False
        for col_name, statuses in _COLUMN_ORDER:
            if goal.status in statuses:
                board.columns[col_name].append(card)
                placed = True
                break
        if not placed:
            board.columns["Backlog"].append(card)

    return board


def render_terminal(board: KanbanBoard) -> str:
    """Rich-Markdown compatible ASCII kanban. For use with Console.print."""
    lines = [f"[bold]Kanban Board[/bold]  ([dim]{board.total_goals} goals[/dim])\n"]
    for col_name, _ in _COLUMN_ORDER:
        cards = board.columns[col_name]
        if not cards and col_name in ("Backlog", "Archived"):
            continue  # skip empty noise columns
        lines.append(f"\n[bold underline]{col_name}[/bold underline]  ({len(cards)})")
        if not cards:
            lines.append("  [dim]— empty —[/dim]")
            continue
        for card in cards:
            g = card.goal
            title = g.title[:55]
            badges = []
            if card.has_plan:
                badges.append("[blue]plan[/blue]")
            if card.iteration_count:
                badges.append(f"[dim]{card.iteration_count} iter[/dim]")
            if card.retry_count:
                badges.append(f"[yellow]{card.retry_count} retry[/yellow]")
            if card.last_verdict:
                vc = {"PASS": "green", "PUSHED": "cyan", "SURVIVED": "green",
                      "RETRY": "yellow", "BROKEN": "red", "VULNERABLE": "red"}.get(card.last_verdict, "white")
                badges.append(f"[{vc}]{card.last_verdict}[/{vc}]")
            badge_str = "  ".join(badges)
            lines.append(f"  [bold]{title}[/bold]  [dim]{g.id[:20]}[/dim]")
            if badge_str:
                lines.append(f"    {badge_str}")
            if card.pr_url:
                lines.append(f"    [dim]PR: {card.pr_url}[/dim]")
    return "\n".join(lines)


def render_markdown(board: KanbanBoard) -> str:
    """Markdown kanban for wiki pasting."""
    lines = ["# Kanban Board", f"_{board.total_goals} goals total_", ""]
    for col_name, _ in _COLUMN_ORDER:
        cards = board.columns[col_name]
        if not cards and col_name in ("Backlog", "Archived"):
            continue
        lines.append(f"## {col_name} ({len(cards)})")
        if not cards:
            lines.append("_empty_")
            lines.append("")
            continue
        for card in cards:
            g = card.goal
            checklist_mark = "✓" if card.last_verdict in ("PASS", "PUSHED", "SURVIVED") else "·"
            suffix = []
            if card.has_plan:
                suffix.append("plan locked")
            if card.iteration_count:
                suffix.append(f"{card.iteration_count} iter")
            if card.retry_count:
                suffix.append(f"{card.retry_count} retry")
            if card.last_verdict:
                suffix.append(card.last_verdict)
            suffix_str = " — " + ", ".join(suffix) if suffix else ""
            lines.append(f"- {checklist_mark} **{g.title}** `{g.id}`{suffix_str}")
            if card.pr_url:
                lines.append(f"  - PR: {card.pr_url}")
        lines.append("")
    return "\n".join(lines)


def render_jira(board: KanbanBoard) -> str:
    """JIRA wiki markup version — for use in JIRA ticket description field."""
    md = render_markdown(board)
    import re
    out = []
    for line in md.splitlines():
        if line.startswith("## "):
            out.append("h2. " + line[3:])
        elif line.startswith("# "):
            out.append("h1. " + line[2:])
        else:
            line = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", line)
            line = re.sub(r"`([^`]+)`", r"{{\1}}", line)
            out.append(line)
    return "\n".join(out)
