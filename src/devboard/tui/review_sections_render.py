"""Review tab renderer — As-Is → To-Be risk framing.

Improved = risks planned AND resolved during execution.
ToImprove = risks planned but unresolved + new known_risks surfaced mid-run.
Learned = learnings.jsonl entries.
TODOs = non_goals (deferred followups).

All 4 sections use text labels (no emoji) per borderline decision — terminal
font independent, snapshot stable.
"""

from __future__ import annotations

from typing import Any


def _fmt_step(s: dict[str, Any]) -> str:
    return f"  • {s.get('id', '?')}  {s.get('behavior', '')}"


def _fmt_learning(l: dict[str, Any]) -> str:
    conf = l.get("confidence", 0.0)
    try:
        conf_f = float(conf)
    except (TypeError, ValueError):
        conf_f = 0.0
    snippet = str(l.get("content", ""))[:120]
    return f"  • {l.get('name', '?')} (conf {conf_f:.1f}) — {snippet}"


def render_review_sections(payload: dict[str, Any]) -> str:
    risk = payload.get("risk_delta") or {}
    resolved = risk.get("resolved") or []
    remaining = risk.get("remaining") or []
    learnings = payload.get("learnings") or []

    # Fallback to completed/non-completed steps when risk_delta is empty
    # (e.g. unit tests that seed only plan_digest).
    use_steps_fallback = not resolved and not remaining
    plan = payload.get("plan_digest") or {}
    steps = plan.get("atomic_steps") or []
    improved_steps = [s for s in steps if s.get("completed")]
    to_improve_steps = [s for s in steps if not s.get("completed")]
    followups = (
        risk.get("followups") if risk.get("followups")
        else payload.get("followups") or []
    )

    lines: list[str] = []
    lines.append("## Improved (resolved during this task)")
    if use_steps_fallback:
        # Legacy unit-test compat: show completed steps as "improved".
        if improved_steps:
            lines.extend(_fmt_step(s) for s in improved_steps)
        else:
            lines.append("  (none yet)")
    else:
        if resolved:
            for r in resolved:
                lines.append(f"  • {r}")
        else:
            lines.append("  (none yet)")
    lines.append("")

    lines.append("## ToImprove (risks remaining / newly surfaced)")
    if use_steps_fallback:
        if to_improve_steps:
            lines.extend(_fmt_step(s) for s in to_improve_steps)
        else:
            lines.append("  (all planned steps complete)")
    else:
        if remaining:
            for r in remaining:
                # Trim long risk strings for scanability.
                text = r if len(r) <= 160 else r[:157] + "…"
                lines.append(f"  • {text}")
        else:
            lines.append("  (none)")
    lines.append("")

    lines.append("## Learned")
    if learnings:
        lines.extend(_fmt_learning(l) for l in learnings)
    else:
        lines.append("  (no learnings captured)")
    lines.append("")

    lines.append("## TODOs (follow-up work)")
    if followups:
        for f in followups:
            lines.append(f"  □ {f}")
    else:
        lines.append("  (none)")
    return "\n".join(lines)
