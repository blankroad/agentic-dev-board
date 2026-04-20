"""Overview tab renderer: 4 sections from OverviewPayload dict."""

from __future__ import annotations

from typing import Any


def _fmt_iteration_row(it: dict[str, Any]) -> str:
    stats = it.get("diff_stats") or {}
    adds = stats.get("adds", 0)
    dels = stats.get("dels", 0)
    files = it.get("touched_files") or []
    file_str = ", ".join(files[:2]) + ("…" if len(files) > 2 else "")
    return (
        f"  iter {it.get('iter', '?'):>3}  {str(it.get('phase', '?')):<14}"
        f"  {str(it.get('verdict', '?')):<16}  "
        f"(+{adds} −{dels})  {file_str}"
    )


def render_overview_body(payload: dict[str, Any]) -> str:
    purpose = payload.get("purpose") or "_not set_"
    plan = payload.get("plan_digest") or {}
    iters = payload.get("iterations") or []
    state = payload.get("current_state") or {}

    lines: list[str] = []
    lines.append("## 목적 (Purpose)")
    lines.append(f"  {purpose}")
    lines.append("")
    lines.append("## 계획 요약 (Plan digest)")
    lines.append(f"  • locked_hash     : {plan.get('locked_hash', '-')}")
    lines.append(f"  • scope_decision  : {plan.get('scope_decision', '-')}")
    total = plan.get("atomic_steps_total", 0)
    done = plan.get("atomic_steps_done", 0)
    lines.append(f"  • atomic_steps    : {total}  ({done} done)")
    lines.append("")
    lines.append("## 활동 (Activity — iter timeline 요약)")
    if not iters:
        lines.append("  (아직 활동 없음)")
    else:
        for it in iters[-6:]:
            lines.append(_fmt_iteration_row(it))
        if len(iters) > 6:
            lines.append(f"  … (+{len(iters) - 6} older iters — Dev 탭에서 전체 보기)")
    lines.append("")
    lines.append("## 현재 상태 · 최종 동작 (Current state)")
    lines.append(f"  status : {state.get('status', '-')}")
    if "last_iter" in state:
        lines.append(f"  last   : iter {state['last_iter']}  "
                     f"{state.get('last_phase', '')}  {state.get('last_verdict', '')}")
        if state.get("last_ts"):
            lines.append(f"  ts     : {state['last_ts']}")
    return "\n".join(lines)
