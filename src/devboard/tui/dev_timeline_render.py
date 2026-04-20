"""Dev tab renderer: per-iter block, oldest-top chronological."""

from __future__ import annotations

from typing import Any


def _iter_block(it: dict[str, Any]) -> list[str]:
    stats = it.get("diff_stats") or {}
    adds = stats.get("adds", 0)
    dels = stats.get("dels", 0)
    lines = [
        f"iter {it.get('iter', '?')} · {it.get('phase', '?')} · "
        f"{it.get('verdict', '?')}     {it.get('ts', '')}",
        f"  delta : +{adds} −{dels}",
    ]
    files = it.get("touched_files") or []
    if files:
        lines.append("  files :")
        for p in files:
            lines.append(f"    ~ {p}")
    else:
        lines.append("  files : (none)")
    return lines


def render_dev_timeline(payload: dict[str, Any]) -> str:
    iters = payload.get("iterations") or []
    if not iters:
        return "(아직 활동 없음 — tdd 사이클 시작 전)"
    # oldest-top: payload.iterations is already sorted asc by _extract_iterations
    blocks: list[str] = []
    for it in iters:
        blocks.extend(_iter_block(it))
        blocks.append("")
    return "\n".join(blocks).rstrip()
