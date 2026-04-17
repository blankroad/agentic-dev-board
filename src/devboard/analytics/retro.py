from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from devboard.orchestrator.checkpointer import Checkpointer
from devboard.storage.file_store import FileStore


@dataclass
class GoalStats:
    goal_id: str
    title: str
    tasks: int = 0
    iterations: int = 0
    reviews: int = 0
    retries: int = 0
    passes: int = 0
    iron_law_hits: int = 0
    redteam_broken: int = 0
    rca_escalations: int = 0
    converged: bool = False


@dataclass
class RetroReport:
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    goal_stats: list[GoalStats] = field(default_factory=list)
    top_failure_modes: list[tuple[str, int]] = field(default_factory=list)
    learnings_promoted: int = 0
    total_runs: int = 0
    converged_runs: int = 0
    blocked_runs: int = 0

    def to_markdown(self) -> str:
        lines = [f"# devboard Retrospective", f"_generated: {self.generated_at}_", ""]
        lines.append(f"## Runs")
        lines.append(f"- Total runs: **{self.total_runs}**")
        lines.append(f"- Converged: **{self.converged_runs}**")
        lines.append(f"- Blocked: **{self.blocked_runs}**")
        if self.total_runs:
            pct = 100 * self.converged_runs / self.total_runs
            lines.append(f"- Convergence rate: **{pct:.0f}%**")
        lines.append("")

        lines.append("## Per-Goal Stats")
        if not self.goal_stats:
            lines.append("_(no goals)_")
        for g in self.goal_stats:
            status = "✓ converged" if g.converged else "blocked/active"
            lines.append(f"### {g.title}  `{g.goal_id[:16]}` — {status}")
            lines.append(f"- Tasks: {g.tasks}")
            lines.append(f"- Iterations: {g.iterations}")
            lines.append(f"- Reviews: {g.reviews} (retries: {g.retries}, passes: {g.passes})")
            if g.iron_law_hits:
                lines.append(f"- ⚠ Iron Law violations: {g.iron_law_hits}")
            if g.redteam_broken:
                lines.append(f"- Red-team BROKEN verdicts: {g.redteam_broken}")
            if g.rca_escalations:
                lines.append(f"- RCA escalations: {g.rca_escalations}")
            lines.append("")

        lines.append("## Top Failure Modes")
        if not self.top_failure_modes:
            lines.append("_(none recorded)_")
        for mode, count in self.top_failure_modes[:5]:
            lines.append(f"- `{mode}` × {count}")
        lines.append("")

        lines.append(f"## Learnings Promoted: {self.learnings_promoted}")
        return "\n".join(lines)


def _collect_goal_stats(store: FileStore, goal_id: str, title: str) -> GoalStats:
    stats = GoalStats(goal_id=goal_id, title=title)
    goal = store.load_goal(goal_id)
    if goal is None:
        return stats
    stats.tasks = len(goal.task_ids)

    from devboard.models import GoalStatus
    stats.converged = goal.status in (GoalStatus.converged, GoalStatus.awaiting_approval, GoalStatus.pushed)

    for task_id in goal.task_ids:
        entries = store.load_decisions(task_id)
        for e in entries:
            phase = e.phase
            source = (e.verdict_source or "").upper()
            if phase == "review":
                stats.reviews += 1
                if "RETRY" in source or "RETRY" in e.reasoning.upper():
                    stats.retries += 1
                if "PASS" in source or "PASS" in e.reasoning.upper():
                    stats.passes += 1
            elif phase == "iron_law":
                stats.iron_law_hits += 1
            elif phase == "redteam" and "BROKEN" in source:
                stats.redteam_broken += 1
            elif phase == "reflect" and "ESCALATE" in e.reasoning.upper():
                stats.rca_escalations += 1
        # Iteration count = unique iter numbers in decisions
        iters = {e.iter for e in entries}
        stats.iterations = max(stats.iterations, len(iters))

    return stats


def _collect_failure_modes(store: FileStore, goal_ids: list[str]) -> Counter:
    counter: Counter = Counter()
    for goal_id in goal_ids:
        goal = store.load_goal(goal_id)
        if goal is None:
            continue
        for task_id in goal.task_ids:
            for e in store.load_decisions(task_id):
                if e.phase == "reflect" and e.reasoning:
                    # First line of root cause as failure-mode key
                    key = e.reasoning.splitlines()[0][:80].strip()
                    if key:
                        counter[key] += 1
    return counter


def _collect_run_outcomes(store: FileStore) -> tuple[int, int, int]:
    runs_dir = store.root / ".devboard" / "runs"
    if not runs_dir.exists():
        return 0, 0, 0
    total = converged = blocked = 0
    for p in runs_dir.glob("*.jsonl"):
        total += 1
        cp = Checkpointer(p)
        events = [e.get("event") for e in cp.load_all()]
        if "converged" in events:
            converged += 1
        elif "blocked" in events:
            blocked += 1
    return total, converged, blocked


def generate_retro(
    store: FileStore,
    goal_id: str | None = None,
    last_n_goals: int | None = None,
) -> RetroReport:
    board = store.load_board()
    goals = board.goals
    if goal_id:
        goals = [g for g in goals if g.id == goal_id]
    elif last_n_goals:
        goals = sorted(goals, key=lambda g: g.created_at, reverse=True)[:last_n_goals]

    report = RetroReport()
    report.goal_stats = [_collect_goal_stats(store, g.id, g.title) for g in goals]
    report.top_failure_modes = _collect_failure_modes(store, [g.id for g in goals]).most_common(10)
    report.learnings_promoted = len(store.list_learnings())
    report.total_runs, report.converged_runs, report.blocked_runs = _collect_run_outcomes(store)
    return report


def save_retro(store: FileStore, report: RetroReport) -> Path:
    retros_dir = store.root / ".devboard" / "retros"
    retros_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = retros_dir / f"retro_{date}.md"
    path.write_text(report.to_markdown())
    return path
