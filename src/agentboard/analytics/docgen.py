"""Design document generator — produces a narrative describing what was built,
why, and how. Output targets: markdown (universal), jira wiki markup, confluence
wiki markup. Source of truth: LockedPlan + decisions.jsonl + runs + iter diffs.

This is the artifact that feeds JIRA tickets / Confluence pages / PR descriptions.
Not a raw dump — interprets the development arc into a maintainable story.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agentboard.models import DecisionEntry, Goal, LockedPlan, Task
from agentboard.storage.file_store import FileStore

Format = Literal["md", "jira", "confluence"]


@dataclass
class DesignDoc:
    goal: Goal
    plan: LockedPlan | None
    tasks: list[Task]
    decisions_by_task: dict[str, list[DecisionEntry]] = field(default_factory=dict)
    gauntlet_steps: dict[str, str] = field(default_factory=dict)  # step_name → content
    git_commits: list[str] = field(default_factory=list)
    pr_url: str = ""

    def to_markdown(self) -> str:
        return _render_md(self)

    def to_jira(self) -> str:
        return _render_jira(self)

    def to_confluence(self) -> str:
        return _render_confluence(self)

    def render(self, fmt: Format = "md") -> str:
        return {"md": self.to_markdown, "jira": self.to_jira,
                "confluence": self.to_confluence}[fmt]()


def collect_doc(store: FileStore, goal_id: str) -> DesignDoc:
    goal = store.load_goal(goal_id)
    if goal is None:
        raise ValueError(f"Goal not found: {goal_id}")

    plan = store.load_locked_plan(goal_id)
    tasks = [t for t in (store.load_task(goal_id, tid) for tid in goal.task_ids) if t]
    decisions_by_task = {t.id: store.load_decisions(t.id) for t in tasks}

    gauntlet_dir = store.root / ".agentboard" / "goals" / goal_id / "gauntlet"
    gauntlet_steps = {}
    if gauntlet_dir.exists():
        for f in gauntlet_dir.glob("*.md"):
            gauntlet_steps[f.stem] = f.read_text()

    # PR url from approval decision if present
    pr_url = ""
    for task_decisions in decisions_by_task.values():
        for d in task_decisions:
            if d.phase == "approval" and "https://" in d.reasoning:
                import re
                m = re.search(r"https?://\S+", d.reasoning)
                if m:
                    pr_url = m.group(0).rstrip(".,)")
                    break
        if pr_url:
            break

    return DesignDoc(
        goal=goal, plan=plan, tasks=tasks,
        decisions_by_task=decisions_by_task,
        gauntlet_steps=gauntlet_steps,
        pr_url=pr_url,
    )


# ── Markdown ──────────────────────────────────────────────────────────────────

def _render_md(doc: DesignDoc) -> str:
    lines: list[str] = []
    g = doc.goal
    p = doc.plan

    lines.append(f"# {g.title}")
    lines.append(f"> Goal `{g.id}` · Status **{g.status.value}**"
                 + (f" · Locked hash `{p.locked_hash}`" if p else ""))
    lines.append("")

    # Problem
    if p and p.problem:
        lines.append("## Problem")
        lines.append(p.problem)
        lines.append("")

    # Architecture
    if p and p.architecture:
        lines.append("## Architecture")
        lines.append(p.architecture)
        lines.append("")

    # Scope & budget
    if p:
        lines.append("## Scope & Budget")
        lines.append(f"- Scope decision: **{p.scope_decision}**")
        lines.append(f"- Token ceiling: {p.token_ceiling:,}")
        lines.append(f"- Max iterations: {p.max_iterations}")
        if p.non_goals:
            lines.append("- Non-goals:")
            for ng in p.non_goals:
                lines.append(f"  - {ng}")
        if p.out_of_scope_guard:
            lines.append("- Out-of-scope guard:")
            for og in p.out_of_scope_guard:
                lines.append(f"  - `{og}`")
        lines.append("")

    # Success criteria
    if p and p.goal_checklist:
        lines.append("## Success Criteria")
        all_decisions = [d for ds in doc.decisions_by_task.values() for d in ds]
        done = (
            any(d.phase == "approval" and d.verdict_source == "PUSHED" for d in all_decisions)
            or any(d.phase == "review" and "PASS" in (d.verdict_source or "") for d in all_decisions)
            or any(t.status.value in ("pushed", "converged") for t in doc.tasks)
        )
        for item in p.goal_checklist:
            mark = "x" if done else " "
            lines.append(f"- [{mark}] {item}")
        lines.append("")

    # Atomic step rundown
    if p and p.atomic_steps:
        lines.append("## Atomic Steps")
        for s in p.atomic_steps:
            lines.append(f"- **{s.id}** — {s.behavior}")
            lines.append(f"  - test: `{s.test_file}::{s.test_name}`")
            if s.impl_file:
                lines.append(f"  - impl: `{s.impl_file}`")
        lines.append("")

    # Decision narrative — per task, chronological
    for task in doc.tasks:
        decs = doc.decisions_by_task.get(task.id, [])
        if not decs:
            continue
        lines.append(f"## Development Arc — {task.title}")
        lines.append("")

        # Group by iteration
        by_iter: dict[int, list[DecisionEntry]] = {}
        for d in decs:
            by_iter.setdefault(d.iter, []).append(d)

        for i in sorted(by_iter.keys()):
            lines.append(f"### Iteration {i}")
            for d in by_iter[i]:
                phase_label = d.phase.replace("_", " ").title()
                verdict = f" — **{d.verdict_source}**" if d.verdict_source else ""
                lines.append(f"- **{phase_label}**{verdict}")
                # Show reasoning, truncated if long
                reason = d.reasoning or ""
                if reason:
                    # First 2 lines
                    for line in reason.splitlines()[:2]:
                        if line.strip():
                            lines.append(f"  - {line.strip()[:200]}")
                    if d.next_strategy:
                        lines.append(f"  - → {d.next_strategy[:160]}")
            lines.append("")

    # Review verdicts (collapsed summary)
    all_decs = [d for ds in doc.decisions_by_task.values() for d in ds]
    review_phases = [d for d in all_decs if d.phase in ("review", "cso", "redteam", "approval")]
    if review_phases:
        lines.append("## Review Verdicts")
        for d in review_phases:
            phase = d.phase.upper()
            verdict = d.verdict_source or "?"
            lines.append(f"- **{phase}** (iter {d.iter}): {verdict}")
        lines.append("")

    # Violations
    violations = [d for d in all_decs
                  if d.phase == "iron_law"
                  or "ESCALATED" in (d.verdict_source or "")
                  or "VULNERABLE" in (d.verdict_source or "")
                  or "BROKEN" in (d.verdict_source or "")]
    if violations:
        lines.append("## Issues Found During Development")
        for d in violations:
            lines.append(f"- iter {d.iter} **{d.phase}** ({d.verdict_source}): {d.reasoning[:200]}")
        lines.append("")

    # Artifacts
    lines.append("## Artifacts")
    if p and p.atomic_steps:
        files = set()
        for s in p.atomic_steps:
            if s.test_file: files.add(s.test_file)
            if s.impl_file: files.add(s.impl_file)
        if files:
            lines.append("- Files touched:")
            for f in sorted(files):
                lines.append(f"  - `{f}`")
    if doc.pr_url:
        lines.append(f"- PR: {doc.pr_url}")
    lines.append(f"- agentboard goal: `{g.id}`")
    lines.append("")

    # Maintenance notes
    lines.append("## For Maintainers")
    if p and p.known_failure_modes:
        lines.append("### Known failure modes (from Gauntlet Challenge step)")
        for m in p.known_failure_modes:
            lines.append(f"- {m}")
        lines.append("")
    if p and p.out_of_scope_guard:
        lines.append("### Do not touch (out-of-scope guard)")
        for og in p.out_of_scope_guard:
            lines.append(f"- `{og}`")
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated by agentboard from `{g.id}`. Raw state: `.agentboard/goals/{g.id}/`_")

    return "\n".join(lines) + "\n"


# ── JIRA wiki markup ──────────────────────────────────────────────────────────

def _render_jira(doc: DesignDoc) -> str:
    md = _render_md(doc)
    # Convert markdown to JIRA wiki markup
    # Headings: # → h1., ## → h2., ### → h3., #### → h4.
    # Bold: **x** → *x*
    # Code: `x` → {{x}}
    # Lists: -  → * (stay same level)
    # Blockquote > → bq.
    import re
    out = []
    for line in md.splitlines():
        # Headings
        if line.startswith("#### "):
            out.append("h4. " + line[5:]); continue
        if line.startswith("### "):
            out.append("h3. " + line[4:]); continue
        if line.startswith("## "):
            out.append("h2. " + line[3:]); continue
        if line.startswith("# "):
            out.append("h1. " + line[2:]); continue
        # Blockquote
        if line.startswith("> "):
            out.append("bq. " + line[2:]); continue
        # Bold **x** → *x*
        line = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", line)
        # Inline code `x` → {{x}}
        line = re.sub(r"`([^`]+)`", r"{{\1}}", line)
        # Checklist [x] → ✓, [ ] → ☐
        line = re.sub(r"^(\s*)- \[x\] ", r"\1* ✓ ", line)
        line = re.sub(r"^(\s*)- \[ \] ", r"\1* ☐ ", line)
        # Unordered list - → *
        line = re.sub(r"^(\s*)- ", lambda m: m.group(1) + "*" * (len(m.group(1))//2 + 1) + " ", line)
        out.append(line)
    return "\n".join(out)


# ── Confluence wiki markup ────────────────────────────────────────────────────

def _render_confluence(doc: DesignDoc) -> str:
    """Confluence supports 'wiki markup' input; this is similar to JIRA but with
    some differences (e.g., code panels use {code}{code} blocks)."""
    # Confluence wiki markup is close enough to JIRA's format that we can reuse,
    # with a couple of additions for Confluence-specific features.
    return _render_jira(doc)
