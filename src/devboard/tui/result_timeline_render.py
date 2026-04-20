"""Result tab renderer: atomic_steps checklist + per-iter completion ts."""

from __future__ import annotations

from typing import Any


def render_result_timeline(payload: dict[str, Any]) -> str:
    plan = payload.get("plan_digest") or {}
    steps = plan.get("atomic_steps") or []
    if not steps:
        return "_Plan not locked._"
    total = plan.get("atomic_steps_total") or len(steps)
    done = plan.get("atomic_steps_done") or sum(1 for s in steps if s.get("completed"))

    iters = payload.get("iterations") or []
    # Map each GREEN iter to its timestamp — used to annotate completed steps
    # in order. Simplification: i-th completed step gets i-th green iter ts.
    green_ts: list[str] = [
        str(it.get("ts", "")) for it in iters
        if str(it.get("phase", "")).startswith("tdd_green")
    ]

    lines: list[str] = [f"[{done}/{total} done]", ""]
    done_idx = 0
    for s in steps:
        mark = "[x]" if s.get("completed") else "[ ]"
        row = f"{mark} {s.get('id', '?')}  {s.get('behavior', '')}"
        if s.get("completed") and done_idx < len(green_ts):
            row += f"    ✓ {green_ts[done_idx]}"
            done_idx += 1
        lines.append(row)
    return "\n".join(lines)
