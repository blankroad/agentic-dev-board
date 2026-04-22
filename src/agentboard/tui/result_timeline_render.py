"""Result tab renderer: Plan vs execution, grouped into deliverables.

Manager/PM view: shipped-count + thematic deliverable bullets, not a flat
list of raw atomic_step assertion strings.
"""

from __future__ import annotations

import re
from typing import Any


# impl_file prefix → deliverable label. First match wins.
_DELIVERABLE_BUCKETS: tuple[tuple[str, str], ...] = (
    ("src/agentboard/tui/overview_render", "Overview renderer"),
    ("src/agentboard/tui/dev_timeline_render", "Dev renderer"),
    ("src/agentboard/tui/result_timeline_render", "Result renderer"),
    ("src/agentboard/tui/review_sections_render", "Review renderer"),
    ("src/agentboard/tui/phase_flow", "PhaseFlowView integration"),
    ("src/agentboard/tui/app", "app-level bindings"),
    ("src/agentboard/analytics/overview_payload", "OverviewPayload builder"),
    ("src/agentboard/analytics/iter_diffstat", "numstat parser"),
    ("src/agentboard/mcp_server", "MCP tool registration"),
    ("tests/test_phase_flow", "phase_flow tests"),
    ("tests/", "test coverage"),
)


def _deliverable_label_for_step(s: dict[str, Any]) -> str:
    impl = str(s.get("impl_file", "") or "")
    if impl:
        for prefix, label in _DELIVERABLE_BUCKETS:
            if impl.startswith(prefix):
                return label
    # Fallback: try to infer from behavior text keywords.
    beh = str(s.get("behavior", "")).lower()
    if "parse_numstat" in beh:
        return "numstat parser"
    if "build_overview_payload" in beh:
        return "OverviewPayload builder"
    if "mcp tool" in beh or "agentboard_build_overview" in beh:
        return "MCP tool registration"
    if "render_overview" in beh:
        return "Overview renderer"
    if "render_dev_timeline" in beh:
        return "Dev renderer"
    if "render_result_timeline" in beh:
        return "Result renderer"
    if "render_review_sections" in beh:
        return "Review renderer"
    if "phaseflowview" in beh or "tabpane" in beh:
        return "PhaseFlowView integration"
    if "agentboardapp" in beh or "keybinding" in beh or "activate_tab" in beh:
        return "app-level bindings"
    if "test_phase_flow" in beh:
        return "phase_flow tests"
    return "other"


def render_result_timeline(payload: dict[str, Any]) -> str:
    shipping = payload.get("step_shipping") or []
    plan = payload.get("plan_digest") or {}

    if not shipping:
        # Legacy fallback for unit tests that seed only plan_digest.
        steps = plan.get("atomic_steps") or []
        if not steps:
            return "_Plan not locked._"
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
    shipped_n = sum(1 for s in shipping if s.get("shipped"))

    # Count iterations executed (distinct iter numbers across all decisions) —
    # pulled from ship_iter which is the GREEN iter; blocked steps get None.
    green_iters = {
        s.get("ship_iter") for s in shipping if s.get("ship_iter") is not None
    }
    iter_count = max(green_iters) if green_iters else 0

    # Group steps into deliverables.
    by_deliv: dict[str, list[dict[str, Any]]] = {}
    for s in shipping:
        label = _deliverable_label_for_step(s)
        by_deliv.setdefault(label, []).append(s)

    # Order deliverables by their deepest shipped iter (ship order).
    def _latest_iter(steps: list[dict[str, Any]]) -> int:
        return max(
            (int(s.get("ship_iter") or 0) for s in steps),
            default=0,
        )

    ordered = sorted(by_deliv.items(), key=lambda kv: _latest_iter(kv[1]))

    lines = [
        "## Plan vs execution",
        f"  Planned : {total} atomic_steps",
        f"  Shipped : {shipped_n}/{total}"
        + (f"  (through iter {iter_count})" if iter_count else ""),
        "",
        "## Deliverables",
    ]
    for label, group in ordered:
        group_done = sum(1 for s in group if s.get("shipped"))
        mark = "✓" if group_done == len(group) else "~"
        iters = sorted(
            {int(s.get("ship_iter") or 0) for s in group if s.get("ship_iter") is not None}
        )
        iter_str = ""
        if iters:
            iter_str = f"  · iter {_fmt_iter_range(iters)}"
        lines.append(f"  {mark} {label:<28} {group_done}/{len(group)}{iter_str}")

    # Pending steps, if any.
    pending = [s for s in shipping if not s.get("shipped")]
    if pending:
        lines.append("")
        lines.append("## Pending")
        for s in pending:
            lines.append(f"  [ ] {s.get('id', '?')}  {str(s.get('behavior', ''))[:80]}")

    return "\n".join(lines)


def _fmt_iter_range(iters: list[int]) -> str:
    """Compact "1,2,3,5" → "1-3,5" rendering."""
    if not iters:
        return ""
    runs: list[tuple[int, int]] = []
    start = prev = iters[0]
    for n in iters[1:]:
        if n == prev + 1:
            prev = n
            continue
        runs.append((start, prev))
        start = prev = n
    runs.append((start, prev))
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)
