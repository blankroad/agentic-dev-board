"""Result tab renderer — empirical evidence layer.

Audience = a developer or future agent code-reviewing a goal after the fact.
They want to see what shipped, how it was verified, and what's still open.
They do NOT want iter-by-iter sparklines or swimlanes (those widgets were
retired with the Plan-tab redesign).

Sections:
- ## Outcome                — template-generated one-liner
- ## Goal checklist         — DataTable-shaped
- ## Atomic steps shipping  — DataTable from step_shipping
- ## Verification chain     — Mermaid flowchart from decisions phase sequence
- ## Pending                — unshipped atomic_steps, conditional
"""

from __future__ import annotations

from typing import Any, Iterable


_VERIFICATION_PHASES: tuple[str, ...] = (
    "review",
    "cso",
    "redteam",
    "parallel_review",
    "approval",
)


def render_result_timeline(
    payload: dict[str, Any],
    decisions: list[dict[str, Any]] | None = None,
) -> str:
    decisions = decisions or []
    plan = payload.get("plan_digest") or {}
    shipping = payload.get("step_shipping") or []
    atomic_steps = plan.get("atomic_steps") or []
    checklist = plan.get("goal_checklist") or []

    # Legacy fallback — same contract as the prior renderer so test fixtures
    # that seed nothing still get a meaningful message.
    if not atomic_steps and not checklist and not shipping:
        return "_Plan not locked._"

    sections: list[str] = [_render_outcome(shipping, atomic_steps, decisions)]

    if checklist:
        sections.append(_render_checklist(checklist))

    if atomic_steps or shipping:
        sections.append(_render_shipping_table(atomic_steps, shipping))

    chain = _build_verification_mermaid(decisions)
    if chain:
        sections.append("## Verification chain\n\n```mermaid\n" + chain + "\n```")

    pending_section = _render_pending(shipping, atomic_steps)
    if pending_section:
        sections.append(pending_section)

    return "\n\n".join(sections)


# ── Outcome ──────────────────────────────────────────────────────────────


def _render_outcome(
    shipping: list[dict[str, Any]],
    atomic_steps: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> str:
    total = len(shipping) if shipping else len(atomic_steps)
    if shipping:
        shipped_n = sum(1 for s in shipping if s.get("shipped"))
    else:
        # Legacy fallback: when step_shipping is empty (unit-test fixtures
        # that seed only plan_digest), fall back to the atomic_steps
        # `completed` flag so the Outcome line still reflects progress.
        shipped_n = sum(1 for s in atomic_steps if s.get("completed"))

    verdicts = _final_verdicts(decisions)

    parts: list[str] = []
    if total:
        parts.append(f"Shipped : {shipped_n}/{total} atomic_steps")
    for phase in ("review", "redteam", "parallel_review", "approval"):
        v = verdicts.get(phase)
        if v:
            parts.append(f"{phase} {v}")
    if not parts:
        return "## Outcome\n_(no outcome data yet — plan locked but no verification run)_"
    return "## Outcome\n" + ". ".join(parts) + "."


def _final_verdicts(decisions: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Walk decisions in order; last-seen verdict per phase wins."""
    out: dict[str, str] = {}
    for d in decisions:
        phase = str(d.get("phase", ""))
        if phase in _VERIFICATION_PHASES:
            v = str(d.get("verdict_source") or d.get("verdict") or "")
            if v:
                out[phase] = v
    return out


# ── Goal checklist ───────────────────────────────────────────────────────


def _render_checklist(checklist: list[Any]) -> str:
    rows = ["| # | Item |", "|---|---|"]
    for i, item in enumerate(checklist, 1):
        rows.append(f"| {i} | {str(item).strip()} |")
    return "## Goal checklist\n\n" + "\n".join(rows)


# ── Atomic steps shipping ────────────────────────────────────────────────


def _render_shipping_table(
    atomic_steps: list[dict[str, Any]],
    shipping: list[dict[str, Any]],
) -> str:
    ship_by_id: dict[str, dict[str, Any]] = {
        str(s.get("id")): s for s in shipping if s.get("id")
    }
    source = atomic_steps if atomic_steps else shipping

    rows = [
        "| ID | Behavior | Impl | Ship iter | Status |",
        "|---|---|---|---|---|",
    ]
    for s in source:
        sid = str(s.get("id", "?"))
        beh = str(s.get("behavior", "")).strip()
        if len(beh) > 70:
            beh = beh[:67].rstrip() + "…"
        impl = s.get("impl_file") or ""
        impl_ref = f"`{impl}`" if impl else "—"
        ship = ship_by_id.get(sid) or (s if shipping else {})
        shipped_ok = bool(ship.get("shipped"))
        ship_iter_raw = ship.get("ship_iter")
        ship_iter = str(ship_iter_raw) if ship_iter_raw is not None else "—"
        # Fall back to `completed` when shipping data is absent (legacy plans
        # seeded only from plan_digest).
        if not shipping:
            shipped_ok = bool(s.get("completed"))
        status = "[x]" if shipped_ok else "[ ]"
        # Marker that includes step id first so tests / scan can grep it.
        rows.append(
            f"| {sid} | {beh} | {impl_ref} | {ship_iter} | {status} {sid} |"
        )
    return "## Atomic steps shipping\n\n" + "\n".join(rows)


# ── Verification chain (Mermaid flowchart) ───────────────────────────────


def _build_verification_mermaid(decisions: Iterable[dict[str, Any]]) -> str:
    """Render the phase × verdict sequence from decisions as a Mermaid flowchart.

    Only includes verification phases (review / cso / redteam / parallel_review /
    approval). Returns an empty string when no verification data is available
    so the caller can skip the section entirely.
    """
    seq: list[tuple[str, str, int]] = []
    for d in decisions:
        phase = str(d.get("phase", ""))
        if phase not in _VERIFICATION_PHASES:
            continue
        verdict = str(d.get("verdict_source") or d.get("verdict") or "").strip()
        iter_n = int(d.get("iter", 0) or 0)
        seq.append((phase, verdict, iter_n))
    if not seq:
        return ""

    lines = ["flowchart LR"]
    nodes: list[str] = []
    for i, (phase, verdict, _iter) in enumerate(seq):
        nid = f"N{i}"
        label = f"{phase}: {verdict}" if verdict else phase
        # Mermaid labels cannot contain unescaped `|` or `[`, keep them simple.
        label_safe = label.replace("[", "(").replace("]", ")").replace("|", "/")
        lines.append(f"  {nid}[{label_safe}]")
        nodes.append(nid)
    for a, b in zip(nodes, nodes[1:]):
        lines.append(f"  {a} --> {b}")
    return "\n".join(lines)


# ── Pending ──────────────────────────────────────────────────────────────


def _render_pending(
    shipping: list[dict[str, Any]],
    atomic_steps: list[dict[str, Any]],
) -> str:
    """Return a Pending section or empty string when nothing is pending."""
    if shipping:
        pending = [s for s in shipping if not s.get("shipped")]
    else:
        pending = [s for s in atomic_steps if not s.get("completed")]
    if not pending:
        return ""
    rows = ["| ID | Behavior |", "|---|---|"]
    for s in pending:
        beh = str(s.get("behavior", "")).strip()
        if len(beh) > 80:
            beh = beh[:77].rstrip() + "…"
        rows.append(f"| {s.get('id', '?')} | {beh} |")
    return "## Pending\n\n" + "\n".join(rows)
