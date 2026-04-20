"""Dev tab renderer: As-Is → To-Be code delta (not a per-iter timeline).

Manager/PM view: what changed between task start and HEAD, not how many
TDD cycles it took. File-level numstat, aggregate totals, one block.
"""

from __future__ import annotations

from typing import Any


def _fmt_file_row(f: dict[str, Any]) -> str:
    adds = f.get("adds", 0)
    dels = f.get("dels", 0)
    if adds == "bin" or dels == "bin":
        return f"    ~ {f.get('path', '?')}  (binary)"
    sign = "+" if dels == 0 else "~"
    return f"    {sign} {f.get('path', '?')}  (+{adds} −{dels})"


def render_dev_timeline(payload: dict[str, Any]) -> str:
    """Render Dev tab. Backwards-compatible fallback to per-iter list when
    the new code_delta is absent (e.g. unit tests that seed only iterations).
    """
    delta = payload.get("code_delta") or {}
    base = delta.get("base_commit") or ""
    head = delta.get("head_commit") or ""
    files = delta.get("files") or []

    # Fallback to iter list when code_delta is empty AND iterations exist —
    # keeps legacy tests green without forcing them to build a git repo.
    if not base and not files:
        iters = payload.get("iterations") or []
        if not iters:
            return "(아직 활동 없음 — tdd 사이클 시작 전)"
        # Legacy minimal timeline (single line per iter), enough for unit tests.
        lines: list[str] = []
        for it in iters:
            stats = it.get("diff_stats") or {}
            lines.append(
                f"iter {it.get('iter', '?')} · {it.get('phase', '?')} · "
                f"{it.get('verdict', '?')}  +{stats.get('adds', 0)} −{stats.get('dels', 0)}"
            )
            touched = it.get("touched_files") or []
            if touched:
                lines.append("  files : " + ", ".join(touched))
            else:
                lines.append("  files : (none)")
        return "\n".join(lines)

    lines: list[str] = []
    lines.append("## Scope baseline")
    lines.append(f"  As-Is : commit {base or '(unknown)'}")
    lines.append(f"  To-Be : commit {head or 'HEAD'}")
    lines.append("")
    lines.append("## Net code change")
    total_adds = delta.get("adds", 0)
    total_dels = delta.get("dels", 0)
    lines.append(f"  total : {len(files)} files  +{total_adds} −{total_dels}")
    lines.append("")
    if files:
        lines.append("## Files")
        for f in files:
            lines.append(_fmt_file_row(f))
    else:
        lines.append("(no files changed between base and HEAD)")
    return "\n".join(lines)
