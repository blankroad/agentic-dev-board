"""Per-session metrics collection and skill-activation diagnostics.

Reads .devboard/runs/*.jsonl + decisions.jsonl across all tasks to compute:
  - Skill activation rate (how often each skill fires vs. how often it *should*)
  - MCP tool call frequency + error rate
  - Average iterations per goal
  - Retry distribution
  - Iron Law violations over time
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from agentboard.storage.file_store import FileStore


@dataclass
class SessionMetrics:
    total_goals: int = 0
    total_runs: int = 0
    converged_runs: int = 0
    blocked_runs: int = 0

    skill_events_by_type: Counter = field(default_factory=Counter)
    phase_log_counts: Counter = field(default_factory=Counter)
    verdict_counts: Counter = field(default_factory=Counter)

    iron_law_hits: int = 0
    rca_escalations: int = 0
    redteam_broken: int = 0
    cso_vulnerable: int = 0

    total_iterations: int = 0
    total_retries: int = 0
    total_passes: int = 0

    most_common_failure_modes: list[tuple[str, int]] = field(default_factory=list)

    @property
    def convergence_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.converged_runs / self.total_runs

    @property
    def retry_rate(self) -> float:
        reviews = self.total_retries + self.total_passes
        if reviews == 0:
            return 0.0
        return self.total_retries / reviews

    def to_dict(self) -> dict:
        return {
            "total_goals": self.total_goals,
            "total_runs": self.total_runs,
            "converged_runs": self.converged_runs,
            "blocked_runs": self.blocked_runs,
            "convergence_rate": round(self.convergence_rate, 3),
            "retry_rate": round(self.retry_rate, 3),
            "total_iterations": self.total_iterations,
            "total_retries": self.total_retries,
            "iron_law_hits": self.iron_law_hits,
            "rca_escalations": self.rca_escalations,
            "redteam_broken": self.redteam_broken,
            "cso_vulnerable": self.cso_vulnerable,
            "skill_events": dict(self.skill_events_by_type.most_common(20)),
            "phase_log_counts": dict(self.phase_log_counts.most_common(20)),
            "verdict_counts": dict(self.verdict_counts.most_common(20)),
            "top_failure_modes": self.most_common_failure_modes[:5],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Metrics Report",
            "",
            f"## Top-line",
            f"- Goals: **{self.total_goals}**",
            f"- Runs: **{self.total_runs}** (converged: {self.converged_runs}, blocked: {self.blocked_runs}, rate: {self.convergence_rate:.0%})",
            f"- Iterations: **{self.total_iterations}** (retry rate: {self.retry_rate:.0%})",
            "",
            f"## Signals",
            f"- Iron Law hits: **{self.iron_law_hits}**",
            f"- RCA escalations: **{self.rca_escalations}**",
            f"- Red-team BROKEN: **{self.redteam_broken}**",
            f"- CSO VULNERABLE: **{self.cso_vulnerable}**",
            "",
            f"## Skill activation (top events)",
        ]
        for name, count in self.skill_events_by_type.most_common(10):
            lines.append(f"- {name}: {count}")

        lines += ["", f"## Top failure modes"]
        for mode, count in self.most_common_failure_modes[:5]:
            lines.append(f"- `{mode}` × {count}")

        return "\n".join(lines)


def collect_metrics(store: FileStore) -> SessionMetrics:
    m = SessionMetrics()

    board = store.load_board()
    m.total_goals = len(board.goals)

    # Runs
    runs_dir = store.root / ".devboard" / "runs"
    if runs_dir.exists():
        for rf in runs_dir.glob("*.jsonl"):
            m.total_runs += 1
            events = []
            for line in rf.read_text().splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            event_names = [e.get("event") for e in events]
            for name in event_names:
                if name:
                    m.skill_events_by_type[name] += 1
            if "converged" in event_names:
                m.converged_runs += 1
            elif "blocked" in event_names:
                m.blocked_runs += 1

    # Decisions
    failure_mode_counter: Counter = Counter()
    for goal in board.goals:
        for task_id in goal.task_ids:
            decisions = store.load_decisions(task_id)
            iters = set()
            for d in decisions:
                iters.add(d.iter)
                m.phase_log_counts[d.phase] += 1
                if d.verdict_source:
                    m.verdict_counts[d.verdict_source] += 1

                if d.phase == "iron_law":
                    m.iron_law_hits += 1
                if d.phase == "reflect" and (d.verdict_source or "").upper() == "RCA_ESCALATED":
                    m.rca_escalations += 1
                if d.phase == "redteam" and (d.verdict_source or "").upper() == "BROKEN":
                    m.redteam_broken += 1
                if d.phase == "cso" and (d.verdict_source or "").upper() == "VULNERABLE":
                    m.cso_vulnerable += 1

                if d.phase == "review":
                    if "RETRY" in (d.verdict_source or "").upper():
                        m.total_retries += 1
                    elif "PASS" in (d.verdict_source or "").upper():
                        m.total_passes += 1

                if d.phase == "reflect" and d.reasoning:
                    first_line = d.reasoning.splitlines()[0][:80].strip()
                    if first_line:
                        failure_mode_counter[first_line] += 1

            m.total_iterations += len(iters)

    m.most_common_failure_modes = failure_mode_counter.most_common(10)
    return m


@dataclass
class DiagnosticResult:
    """Self-diagnostic — analyzes whether skills actually activate."""
    expected_skill_events: list[str] = field(default_factory=list)
    actual_skill_events: Counter = field(default_factory=Counter)
    missing_events: list[str] = field(default_factory=list)
    skill_activation_score: float = 0.0     # 0-1
    suggestions: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Diagnostic Report",
            "",
            f"## Skill activation score: **{self.skill_activation_score:.0%}**",
            "",
            f"## Expected skill events",
        ]
        for e in self.expected_skill_events:
            actual = self.actual_skill_events.get(e, 0)
            status = "✓" if actual > 0 else "✗"
            lines.append(f"- {status} `{e}` — {actual}×")

        if self.missing_events:
            lines += ["", "## Missing events (skills likely did not fire)"]
            for e in self.missing_events:
                lines.append(f"- `{e}`")

        if self.suggestions:
            lines += ["", "## Suggestions"]
            for s in self.suggestions:
                lines.append(f"- {s}")
        return "\n".join(lines)


# Events we would expect from a healthy session running the full pipeline
_EXPECTED_EVENTS = [
    "gauntlet_complete",
    "tdd_red_complete",
    "tdd_green_complete",
    "tdd_refactor_complete",
    "review_complete",
    "tdd_complete",
    "redteam_complete",
    "converged",
]


def diagnose_activations(store: FileStore) -> DiagnosticResult:
    metrics = collect_metrics(store)
    result = DiagnosticResult(
        expected_skill_events=_EXPECTED_EVENTS,
        actual_skill_events=metrics.skill_events_by_type,
    )

    hits = sum(1 for e in _EXPECTED_EVENTS if metrics.skill_events_by_type.get(e, 0) > 0)
    result.skill_activation_score = hits / len(_EXPECTED_EVENTS) if _EXPECTED_EVENTS else 0.0
    result.missing_events = [e for e in _EXPECTED_EVENTS if metrics.skill_events_by_type.get(e, 0) == 0]

    # Suggestions
    if result.skill_activation_score == 0.0:
        result.suggestions.append(
            "No skill events detected. Open Claude Code in a project with .mcp.json + .claude/skills/agentboard-* installed."
        )
        result.suggestions.append(
            "Try explicit invocation: 'use agentboard-gauntlet + agentboard-tdd to build <goal>'"
        )
    elif "gauntlet_complete" not in metrics.skill_events_by_type:
        result.suggestions.append(
            "Gauntlet never completed. Skill description may be too narrow — user goals might be classified as 'trivial'. Strengthen the description or use explicit invocation."
        )
    elif "tdd_green_complete" not in metrics.skill_events_by_type:
        result.suggestions.append(
            "TDD never reached GREEN. Possibly Claude Code is writing code without the RED-GREEN split — check Iron Law hits."
        )

    if metrics.iron_law_hits > 0:
        result.suggestions.append(
            f"Iron Law violated {metrics.iron_law_hits} times. TDD skill description may need reinforcement."
        )

    if metrics.rca_escalations > 0:
        result.suggestions.append(
            f"{metrics.rca_escalations} RCA escalation(s) — architectures may have been under-specified in Gauntlet. Consider more rigorous planning gates."
        )

    return result
