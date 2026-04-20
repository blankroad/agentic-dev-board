"""Assemble `plan_summary.md` 5-section narrative from parsed sources.

Deterministic (no LLM) — every sentence in every section carries a
`(source: ...)` citation pointing at the upstream artifact row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devboard.narrative.sources import (
    PlanSections,
    group_decisions_by_iter,
    parse_plan_sections,
)


_EXCERPT_CAP = 600


def _trim(text: str, cap: int = _EXCERPT_CAP) -> str:
    text = text.strip()
    if len(text) <= cap:
        return text
    return text[:cap].rstrip() + " …"


def assemble_purpose(sections: PlanSections) -> str:
    """Render the ## Purpose section from PlanSections.problem."""
    body = _trim(sections.problem) if sections.problem else (
        "_No Problem section found in plan.md._"
    )
    cite = "(source: plan.md ## Problem)"
    return f"## Purpose\n\n{body} {cite}\n"


def assemble_plan(sections: PlanSections) -> str:
    """Render the ## Plan section by stitching Architecture + Scope
    Decision + Budget with per-source citations."""
    parts: list[str] = []
    if sections.architecture:
        parts.append(
            f"{_trim(sections.architecture)} (source: plan.md ## Architecture)"
        )
    if sections.scope_decision:
        parts.append(
            f"Scope decision: {sections.scope_decision.strip()} "
            f"(source: plan.md ## Scope Decision)"
        )
    if sections.budget:
        parts.append(
            f"Budget: {_trim(sections.budget, 200)} (source: plan.md ## Budget)"
        )
    body = "\n\n".join(parts) if parts else "_No Plan data found in plan.md._"
    return f"## Plan\n\n{body}\n"


def assemble_process(grouped: dict[int, list[dict[str, Any]]]) -> str:
    """Render the ## Process section as a round-by-round redteam listing
    plus a summary of TDD iteration counts drawn from decisions.jsonl."""
    lines: list[str] = []
    # Count phases for a quick preamble
    phase_counts: dict[str, int] = {}
    for rows in grouped.values():
        for r in rows:
            phase = str(r.get("phase", ""))
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

    if phase_counts:
        summary = ", ".join(
            f"{phase}={count}"
            for phase, count in sorted(phase_counts.items())
        )
        lines.append(
            f"Decision-log phase totals: {summary} "
            f"(source: decisions.jsonl aggregate)."
        )

    # Eng_review, review, redteam rows — each gets a per-iter citation
    # so the golden sample's shorthand citations like '(source: iter=7
    # review)' have a token-subset match in the generated output.
    narrated_phases = ("eng_review", "review", "redteam")
    round_index = 0
    for iter_n in sorted(grouped.keys()):
        for r in grouped[iter_n]:
            phase = str(r.get("phase", ""))
            if phase not in narrated_phases:
                continue
            verdict = r.get("verdict_source") or "?"
            reasoning = _trim(str(r.get("reasoning", "")), 200)
            if phase == "redteam":
                round_index += 1
                lines.append(
                    f"Round {round_index} (iter={iter_n}) returned {verdict}. "
                    f"{reasoning} "
                    f"(source: decisions.jsonl iter={iter_n} phase=redteam)."
                )
            else:
                lines.append(
                    f"iter={iter_n} {phase}: {verdict}. {reasoning} "
                    f"(source: decisions.jsonl iter={iter_n} phase={phase})."
                )

    if not lines:
        lines.append("_No iteration data yet — generator ran before TDD started._")

    body = "\n\n".join(lines)
    return f"## Process\n\n{body}\n"


def assemble_result(grouped: dict[int, list[dict[str, Any]]]) -> str:
    """Render the ## Result section from the last review + approval rows."""
    last_review: dict[str, Any] | None = None
    last_approval: dict[str, Any] | None = None
    for iter_n in sorted(grouped.keys()):
        for r in grouped[iter_n]:
            phase = str(r.get("phase"))
            if phase == "review":
                last_review = r
            elif phase == "approval":
                last_approval = r

    parts: list[str] = []
    if last_review:
        iter_n = last_review.get("iter", "?")
        verdict = last_review.get("verdict_source") or "?"
        reasoning = _trim(str(last_review.get("reasoning", "")), 240)
        parts.append(
            f"Final review verdict: {verdict}. {reasoning} "
            f"(source: decisions.jsonl iter={iter_n} phase=review)."
        )
    if last_approval:
        iter_n = last_approval.get("iter", "?")
        verdict = last_approval.get("verdict_source") or "?"
        reasoning = _trim(str(last_approval.get("reasoning", "")), 240)
        parts.append(
            f"Approval outcome: {verdict}. {reasoning} "
            f"(source: decisions.jsonl iter={iter_n} phase=approval)."
        )
    if not parts:
        parts.append("_No review/approval rows found in decisions.jsonl yet._")

    body = "\n\n".join(parts)
    return f"## Result\n\n{body}\n"


def assemble_review(grouped: dict[int, list[dict[str, Any]]]) -> str:
    """Render the ## Review section as a meta-reflection on redteam/cso
    rounds and any known-risk / deferred notes mined from review text."""
    redteam_rows: list[dict[str, Any]] = []
    cso_rows: list[dict[str, Any]] = []
    parallel_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for iter_n in sorted(grouped.keys()):
        for r in grouped[iter_n]:
            phase = str(r.get("phase"))
            if phase == "redteam":
                redteam_rows.append(r)
            elif phase == "cso":
                cso_rows.append(r)
            elif phase == "parallel_review":
                parallel_rows.append(r)
            elif phase == "review":
                review_rows.append(r)

    lines: list[str] = []

    if redteam_rows:
        broken = sum(1 for r in redteam_rows if r.get("verdict_source") == "BROKEN")
        survived = sum(1 for r in redteam_rows if r.get("verdict_source") == "SURVIVED")
        lines.append(
            f"Adversarial review arc: {len(redteam_rows)} redteam round(s) — "
            f"{broken} BROKEN, {survived} SURVIVED "
            f"(source: decisions.jsonl phase=redteam aggregate)."
        )

    if cso_rows:
        last = cso_rows[-1]
        iter_n = last.get("iter", "?")
        verdict = last.get("verdict_source") or "?"
        lines.append(
            f"Security review (CSO) final verdict: {verdict} "
            f"(source: decisions.jsonl iter={iter_n} phase=cso)."
        )

    if parallel_rows:
        last = parallel_rows[-1]
        iter_n = last.get("iter", "?")
        verdict = last.get("verdict_source") or "?"
        lines.append(
            f"Parallel review final verdict: {verdict} "
            f"(source: decisions.jsonl iter={iter_n} phase=parallel_review)."
        )

    # Deferred / known-risk scan across review + redteam reasoning
    risk_hits: list[str] = []
    for r in redteam_rows + review_rows:
        reasoning = str(r.get("reasoning", "")).lower()
        iter_n = r.get("iter", "?")
        phase = r.get("phase", "?")
        for marker in ("deferred", "known-risk", "known_risk"):
            if marker in reasoning:
                risk_hits.append(
                    f"{marker.replace('_', '-')} noted at iter={iter_n} phase={phase} "
                    f"(source: decisions.jsonl iter={iter_n} phase={phase})"
                )
                break
    if risk_hits:
        lines.append(
            "Deferred / known-risk signals: " + "; ".join(risk_hits) + "."
        )

    if not lines:
        lines.append(
            "_No adversarial or review rows yet — this section is populated "
            "once parallel_review and approval complete._"
        )

    body = "\n\n".join(lines)
    return f"## Review\n\n{body}\n"


def generate_narrative(project_root: Path, goal_id: str) -> Path:
    """Compose plan_summary.md for `goal_id` from plan.md + the goal's
    latest task decisions.jsonl. Writes `<project_root>/.devboard/goals/
    <goal_id>/plan_summary.md` and returns the Path.

    Assembly is deterministic: no LLM calls, no network, no randomness.
    """
    goal_dir = project_root / ".devboard" / "goals" / goal_id
    plan_path = goal_dir / "plan.md"
    if not plan_path.exists():
        raise FileNotFoundError(
            f"plan.md not found for goal_id={goal_id!r} at {plan_path}"
        )

    sections = parse_plan_sections(plan_path)

    grouped: dict[int, list[dict[str, Any]]] = {}
    tasks_dir = goal_dir / "tasks"
    if tasks_dir.exists():
        task_dirs = [p for p in tasks_dir.iterdir() if p.is_dir()]
        if task_dirs:
            latest = max(task_dirs, key=lambda p: p.stat().st_mtime)
            decisions_path = latest / "decisions.jsonl"
            if decisions_path.exists():
                grouped = group_decisions_by_iter(decisions_path)

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    title = f"# Goal: {goal_id}"
    meta_line = (
        f"_Auto-generated {now_iso} · sections_parsed: "
        f"{4 - len(sections.missing_sections)}/4"
    )
    if sections.missing_sections:
        meta_line += f" · missing: {', '.join(sections.missing_sections)}"
    meta_line += "_"

    body = "\n".join([
        title,
        "",
        meta_line,
        "",
        assemble_purpose(sections),
        assemble_plan(sections),
        assemble_process(grouped),
        assemble_result(grouped),
        assemble_review(grouped),
    ])

    out_path = goal_dir / "plan_summary.md"
    out_path.write_text(body, encoding="utf-8")
    return out_path
