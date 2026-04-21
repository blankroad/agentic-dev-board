"""Overview metrics — decisions + plan + diff text → 4 MetricCard records
for the Overview tab card strip. Pure function, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MetricCard:
    label: str
    value: str
    hint: str = ""


def _count_changed_files(diff_text: str) -> int:
    if not diff_text:
        return 0
    return sum(1 for line in diff_text.splitlines() if line.startswith("diff --git "))


def _iterations_from_decisions(decisions: list[dict[str, Any]]) -> int:
    iters = set()
    for row in decisions:
        raw = row.get("iter")
        if raw is None:
            continue
        try:
            iters.add(int(raw))
        except (TypeError, ValueError):
            continue
    return len(iters)


def _convergence_from_decisions(decisions: list[dict[str, Any]]) -> str:
    for row in decisions:
        if row.get("phase") == "approval" and row.get("verdict_source") == "PUSHED":
            return "converged"
    if any(r.get("phase") == "review" and r.get("verdict_source") == "PASS" for r in decisions):
        return "review PASS"
    if decisions:
        return "in-progress"
    return "n/a"


def build_metrics(
    decisions: list[dict[str, Any]],
    plan: dict[str, Any],
    diff_text: str,
) -> list[MetricCard]:
    """Build the 4 Overview card records.

    - files_changed: count of `diff --git` markers in `diff_text`
    - iterations: unique `iter` values in decisions
    - convergence: converged / in-progress / n/a based on approval phase
    - tests: atomic_steps_count from plan (first-pass proxy, live counts
      need a future goal)
    """
    files_changed = _count_changed_files(diff_text)
    iterations = _iterations_from_decisions(decisions)
    convergence = _convergence_from_decisions(decisions)
    atomic_steps_total = 0
    try:
        steps = plan.get("atomic_steps") if isinstance(plan, dict) else None
        if isinstance(steps, list):
            atomic_steps_total = len(steps)
    except Exception:
        atomic_steps_total = 0

    return [
        MetricCard(
            label="files_changed",
            value=str(files_changed) if files_changed else "n/a",
            hint="",
        ),
        MetricCard(
            label="iterations",
            value=str(iterations) if iterations else "n/a",
            hint="",
        ),
        MetricCard(
            label="convergence",
            value=convergence,
            hint="",
        ),
        MetricCard(
            label="tests",
            value=f"{atomic_steps_total} steps" if atomic_steps_total else "n/a",
            hint="",
        ),
    ]
