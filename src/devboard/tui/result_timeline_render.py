"""Result tab renderer: As-Is (plan) → To-Be (execution) per atomic_step.

Uses payload.step_shipping (cross-referenced decisions.jsonl GREEN rows)
so completion reflects reality — NOT plan.json.completed, which is never
updated during execution.
"""

from __future__ import annotations

from typing import Any


def render_result_timeline(payload: dict[str, Any]) -> str:
    # Prefer step_shipping (execution-aware); fallback to plan_digest for
    # unit tests that seed only the legacy shape.
    shipping = payload.get("step_shipping") or []
    plan = payload.get("plan_digest") or {}

    if not shipping:
        steps = plan.get("atomic_steps") or []
        if not steps:
            return "_Plan not locked._"
        # Legacy-compat rendering (plan.json.completed based).
        total = plan.get("atomic_steps_total") or len(steps)
        done = plan.get("atomic_steps_done") or sum(
            1 for s in steps if s.get("completed")
        )
        lines = [f"[{done}/{total} done]", ""]
        iters = payload.get("iterations") or []
        green_ts = [
            str(it.get("ts", "")) for it in iters
            if str(it.get("phase", "")).startswith("tdd_green")
        ]
        done_idx = 0
        for s in steps:
            mark = "[x]" if s.get("completed") else "[ ]"
            row = f"{mark} {s.get('id', '?')}  {s.get('behavior', '')}"
            if s.get("completed") and done_idx < len(green_ts):
                row += f"    ✓ {green_ts[done_idx]}"
                done_idx += 1
            lines.append(row)
        return "\n".join(lines)

    total = len(shipping)
    shipped = sum(1 for s in shipping if s.get("shipped"))

    lines: list[str] = []
    lines.append("## Plan vs execution")
    lines.append(f"  As-Is : {total} atomic_steps queued")
    lines.append(f"  To-Be : {shipped}/{total} shipped")
    lines.append("")
    lines.append("## Steps")
    for s in shipping:
        mark = "[x]" if s.get("shipped") else "[ ]"
        row = f"{mark} {s.get('id', '?')}  {s.get('behavior', '')}"
        if s.get("shipped"):
            ship_iter = s.get("ship_iter")
            ship_ts = str(s.get("ship_ts", ""))
            if ship_iter is not None:
                # Compact ts: keep the HH:MM portion only, drop date+tz noise.
                ts_short = ship_ts.split(" ")[-1][:5] if ship_ts else ""
                row += f"  · iter {ship_iter}"
                if ts_short:
                    row += f" @ {ts_short}"
        lines.append(row)
    return "\n".join(lines)
