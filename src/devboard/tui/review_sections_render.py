"""Review tab renderer: 4 text-label sections.

Per borderline decision: text labels (Improved / ToImprove / Learned / TODOs),
no emoji — terminal-font independent, snapshot-stable.
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
    plan = payload.get("plan_digest") or {}
    steps = plan.get("atomic_steps") or []
    improved = [s for s in steps if s.get("completed")]
    to_improve = [s for s in steps if not s.get("completed")]
    learnings = payload.get("learnings") or []
    followups = payload.get("followups") or []

    lines: list[str] = []
    lines.append("## Improved (개선한 것)")
    if improved:
        lines.extend(_fmt_step(s) for s in improved)
    else:
        lines.append("  (아직 완료된 step 없음)")
    lines.append("")
    lines.append("## ToImprove (앞으로 개선할 것)")
    if to_improve:
        lines.extend(_fmt_step(s) for s in to_improve)
    else:
        lines.append("  (모두 완료)")
    lines.append("")
    lines.append("## Learned (배운 점)")
    if learnings:
        lines.extend(_fmt_learning(l) for l in learnings)
    else:
        lines.append("  (누적된 learnings 없음)")
    lines.append("")
    lines.append("## TODOs (후속 할 일)")
    if followups:
        for f in followups:
            lines.append(f"  □ {f}")
    else:
        lines.append("  (없음)")
    return "\n".join(lines)
