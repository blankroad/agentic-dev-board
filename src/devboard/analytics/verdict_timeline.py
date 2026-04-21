"""verdict_timeline — decisions.jsonl row list → per-reviewer (iter, verdict)
tuple lists, so the Review tab widgets can render iteration×reviewer
matrices without re-parsing decisions for each widget.

Pure function. No I/O here — callers pass already-loaded decision rows.
"""

from __future__ import annotations

from typing import Any

REVIEWER_PHASES: frozenset[str] = frozenset({
    "review",
    "cso",
    "redteam",
    "design_review",
    "parallel_review",
})


def build_matrix(decisions: list[dict[str, Any]]) -> dict[str, list[tuple[int, str]]]:
    """Group decisions by reviewer phase.

    Non-reviewer phases (tdd_red / tdd_green / eng_review / approval / ...)
    are dropped. Missing or malformed rows are skipped silently — this is
    a read-path; we never raise on stale or partial decisions.jsonl.
    """
    matrix: dict[str, list[tuple[int, str]]] = {}
    for row in decisions:
        phase = row.get("phase")
        if phase not in REVIEWER_PHASES:
            continue
        iter_raw = row.get("iter", 0)
        try:
            iter_n = int(iter_raw) if iter_raw is not None else 0
        except (TypeError, ValueError):
            iter_n = 0
        if iter_n < 0:
            iter_n = 0
        verdict = row.get("verdict_source") or ""
        matrix.setdefault(phase, []).append((iter_n, str(verdict)))
    return matrix
