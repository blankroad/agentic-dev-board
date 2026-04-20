"""Dev tab renderer: As-Is → To-Be, aggregated by area (not per-file).

Manager/PM view: total diff + rollup by code area, not a 21-row file list.
"""

from __future__ import annotations

from typing import Any


# Path prefix → display bucket. First match wins, so order matters —
# specific paths before generic ones.
_AREA_BUCKETS: tuple[tuple[str, str], ...] = (
    ("src/devboard/analytics/", "analytics"),
    ("src/devboard/tui/", "tui"),
    ("src/devboard/mcp_server", "MCP server"),
    ("src/devboard/mcp_tools/", "MCP tools"),
    ("src/devboard/storage/", "storage"),
    ("src/devboard/orchestrator/", "orchestrator"),
    ("src/devboard/", "devboard (other)"),
    ("tests/", "tests"),
    (".devboard/", "devboard state"),
    ("tui_snapshots/", "snapshots"),
    ("skills/", "skills"),
    ("hooks/", "hooks"),
    ("docs/", "docs"),
)


def _bucket_for(path: str) -> str:
    for prefix, label in _AREA_BUCKETS:
        if path.startswith(prefix):
            return label
    return "other"


def render_dev_timeline(payload: dict[str, Any]) -> str:
    """Render Dev tab as a rollup. Falls back to legacy per-iter rows when
    code_delta is empty (unit tests, fresh tasks).
    """
    delta = payload.get("code_delta") or {}
    base = delta.get("base_commit") or ""
    head = delta.get("head_commit") or ""
    files = delta.get("files") or []

    if not base and not files:
        # Legacy fallback for unit-test fixtures without a git repo.
        iters = payload.get("iterations") or []
        if not iters:
            return "(아직 활동 없음 — tdd 사이클 시작 전)"
        lines: list[str] = []
        for it in iters:
            stats = it.get("diff_stats") or {}
            lines.append(
                f"iter {it.get('iter', '?')} · {it.get('phase', '?')} · "
                f"{it.get('verdict', '?')}  +{stats.get('adds', 0)} −{stats.get('dels', 0)}"
            )
            touched = it.get("touched_files") or []
            lines.append(
                "  files : " + (", ".join(touched) if touched else "(none)")
            )
        return "\n".join(lines)

    # Group by area.
    buckets: dict[str, dict[str, int]] = {}
    for f in files:
        path = str(f.get("path", ""))
        if not path:
            continue
        label = _bucket_for(path)
        b = buckets.setdefault(label, {"files": 0, "adds": 0, "dels": 0})
        b["files"] += 1
        a = f.get("adds", 0)
        d = f.get("dels", 0)
        if isinstance(a, int):
            b["adds"] += a
        if isinstance(d, int):
            b["dels"] += d
    # Sort by lines-changed descending so biggest contributors surface first.
    ordered = sorted(
        buckets.items(),
        key=lambda kv: (kv[1]["adds"] + kv[1]["dels"]),
        reverse=True,
    )

    total_adds = delta.get("adds", 0)
    total_dels = delta.get("dels", 0)

    lines = [
        "## Scope baseline",
        f"  As-Is : commit {base or '(unknown)'}",
        f"  To-Be : commit {head or 'HEAD'}",
        "",
        "## Net change",
        f"  {len(files)} files · +{total_adds} −{total_dels} lines",
        "",
        "## By area",
    ]
    if ordered:
        for label, b in ordered:
            lines.append(
                f"  {label:<20} {b['files']:>3} file(s)  +{b['adds']} −{b['dels']}"
            )
    else:
        lines.append("  (no files)")
    lines.append("")
    lines.append("_상세 파일별 diff:_ `git show HEAD` / `git diff {base}..HEAD`".format(
        base=base or "<base>"
    ))
    return "\n".join(lines)
