"""Dev tab renderer: As-Is → To-Be, aggregated by area (not per-file).

Manager/PM view: total diff + rollup by code area, not a 21-row file list.
"""

from __future__ import annotations

from typing import Any


# Path prefix → display bucket. First match wins, so order matters —
# specific paths before generic ones.
_AREA_BUCKETS: tuple[tuple[str, str], ...] = (
    ("src/agentboard/analytics/", "analytics"),
    ("src/agentboard/tui/", "tui"),
    ("src/agentboard/mcp_server", "MCP server"),
    ("src/agentboard/mcp_tools/", "MCP tools"),
    ("src/agentboard/storage/", "storage"),
    ("src/agentboard/orchestrator/", "orchestrator"),
    ("src/agentboard/", "agentboard (other)"),
    ("tests/", "tests"),
    (".agentboard/", "agentboard state"),
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


_CARD_DIVIDER = "─" * 72


def _render_iter_card(it: dict[str, Any]) -> str:
    """Render a single per-iter code-review card. Fields come from
    overview_payload._extract_iterations (Phase A): step_id, behavior,
    reasoning, test_file, test_name, impl_file, phase, verdict, ts."""
    header = (
        f"iter {it.get('iter', '?')} · {it.get('step_id', '?')} · "
        f"{it.get('phase', '?')} · {it.get('verdict', '?')}"
    )
    stats = it.get("diff_stats") or {}
    adds = stats.get("adds", 0)
    dels = stats.get("dels", 0)
    if adds or dels:
        header += f"  (+{adds} −{dels})"
    ts = it.get("ts", "")
    if ts:
        header += f"    {ts}"
    lines: list[str] = [header]

    behavior = (it.get("behavior") or "").strip()
    lines.append(
        f"  behavior: {behavior}" if behavior else "  behavior: (not captured)"
    )

    reasoning = (it.get("reasoning") or "").strip()
    if reasoning:
        # Flatten embedded newlines so reasoning doesn't visually bleed
        # into the subsequent `test:`/`impl:` card fields. Multi-paragraph
        # reasoning loses its paragraph breaks but keeps all content —
        # the alternative (indent every continuation by 2 spaces) trades
        # visual tidiness against reading effort.
        reasoning_flat = " ".join(part.strip() for part in reasoning.splitlines() if part.strip())
        lines.append(f"  reasoning: {reasoning_flat}")
    else:
        lines.append("  reasoning: (reasoning not captured)")

    test_file = (it.get("test_file") or "").strip()
    test_name = (it.get("test_name") or "").strip()
    if test_file and test_name:
        lines.append(f"  test: {test_file}::{test_name}")
    elif test_file:
        lines.append(f"  test: {test_file}")
    else:
        lines.append("  test: (not captured)")

    impl_file = (it.get("impl_file") or "").strip()
    lines.append(f"  impl: {impl_file}" if impl_file else "  impl: (no impl)")

    # Secondary: git-observed touched files for the iter (complementary
    # to impl_file, which comes from atomic_steps). Omitted when empty.
    touched = it.get("touched_files") or []
    if touched:
        shown = ", ".join(str(t) for t in touched[:3])
        if len(touched) > 3:
            shown += f" (+{len(touched) - 3} more)"
        lines.append(f"  files: {shown}")

    return "\n".join(lines)


def render_dev_timeline(payload: dict[str, Any]) -> str:
    """Render Dev tab: (optional) code_delta rollup + per-iter code-review
    cards. Cards use fields injected by overview_payload cross-ref."""
    delta = payload.get("code_delta") or {}
    base = delta.get("base_commit") or ""
    head = delta.get("head_commit") or ""
    files = delta.get("files") or []
    has_rollup = bool(base or files)

    iters = payload.get("iterations") or []
    if not has_rollup and not iters:
        return "(아직 활동 없음 — tdd 사이클 시작 전)"

    sections: list[str] = []

    if has_rollup:
        # Group by area for the manager-friendly rollup (unchanged logic).
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
        ordered = sorted(
            buckets.items(),
            key=lambda kv: (kv[1]["adds"] + kv[1]["dels"]),
            reverse=True,
        )

        total_adds = delta.get("adds", 0)
        total_dels = delta.get("dels", 0)

        rollup_lines = [
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
                rollup_lines.append(
                    f"  {label:<20} {b['files']:>3} file(s)  +{b['adds']} −{b['dels']}"
                )
        else:
            rollup_lines.append("  (no files)")
        rollup_lines.append("")
        rollup_lines.append(
            "_상세 파일별 diff:_ `git show HEAD` / `git diff {base}..HEAD`".format(
                base=base or "<base>"
            )
        )
        sections.append("\n".join(rollup_lines))

    if iters:
        card_section: list[str] = ["## Iterations", ""]
        card_blocks: list[str] = [_render_iter_card(it) for it in iters]
        card_section.append(("\n" + _CARD_DIVIDER + "\n\n").join(card_blocks))
        sections.append("\n".join(card_section))

    return "\n\n".join(sections)
