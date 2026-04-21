"""Design Tokens for Agent Dev Board TUI (M1b).

Centralized visual constants for verdict colors, phase colors, spacing
rhythm, motion timing, focus indicator style, and responsive layout
breakpoints. Locked spec from /autoplan Phase 2 Design Review.

All widgets that render colors / spacing MUST import from this module.
No scattered hex literals across widget code.
"""
from __future__ import annotations

# ── Verdict colors (3) ────────────────────────────────────────────
# OK family: SECURE / SURVIVED / GREEN / APPROVED
VERDICT_COLOR_OK = "#3eb489"
# FAIL family: BROKEN / VULNERABLE / RED
VERDICT_COLOR_FAIL = "#e5484d"
# PENDING family: PENDING / SKIPPED / PARTIAL
VERDICT_COLOR_PENDING = "#ff9800"


# ── Phase colors (5) ──────────────────────────────────────────────
PHASE_COLOR_PLAN = "#5ea0ef"      # muted blue: plan / gauntlet / brainstorm
PHASE_COLOR_TDD = "#3eb489"        # green family: tdd / dev
PHASE_COLOR_REVIEW = "#a78bfa"     # purple: review / cso / redteam / parallel
PHASE_COLOR_APPROVAL = "#fbbf24"   # accent/gold: approval
PHASE_COLOR_RCA = "#fb923c"        # orange: rca


# ── Spacing rhythm (Textual cell units) ───────────────────────────
SPACING_S = 4
SPACING_M = 8
SPACING_L = 12


# ── Motion ─────────────────────────────────────────────────────────
MOTION_DRAWER_MS = 150  # ease-out for inline drawer expand/collapse


# ── Focus indicator ────────────────────────────────────────────────
FOCUS_INDICATOR_STYLE = "round"  # Textual border style; bracket markers via CSS


# ── Responsive breakpoints (terminal columns) ─────────────────────
BREAKPOINT_3PANE = 120  # >= 120: 3-pane (file tree / diff / issues rail)
BREAKPOINT_2PANE = 100  # 100-119: 2-pane (rail collapsed to bottom row)
BREAKPOINT_1PANE = 80   # 80-99: 1-pane + tab strip
# < 80: "terminal too narrow" banner (no constant; banner mode is below 1pane)


# ── Phase → color helper ───────────────────────────────────────────
_PHASE_COLOR_MAP = {
    "plan": PHASE_COLOR_PLAN,
    "gauntlet": PHASE_COLOR_PLAN,
    "brainstorm": PHASE_COLOR_PLAN,
    "tdd": PHASE_COLOR_TDD,
    "tdd_red": VERDICT_COLOR_FAIL,
    "tdd_green": VERDICT_COLOR_OK,
    "tdd_refactor": PHASE_COLOR_TDD,
    "dev": PHASE_COLOR_TDD,
    "review": PHASE_COLOR_REVIEW,
    "cso": PHASE_COLOR_REVIEW,
    "redteam": PHASE_COLOR_REVIEW,
    "parallel_review": PHASE_COLOR_REVIEW,
    "approval": PHASE_COLOR_APPROVAL,
    "rca": PHASE_COLOR_RCA,
}


def color_for_phase(phase: str) -> str:
    """Return token color for a phase string. Defaults to a neutral grey
    for unknown phases (FallbackRenderer territory)."""
    return _PHASE_COLOR_MAP.get(phase, "#6b7280")


_VERDICT_COLOR_MAP = {
    "SECURE": VERDICT_COLOR_OK,
    "SURVIVED": VERDICT_COLOR_OK,
    "GREEN": VERDICT_COLOR_OK,
    "APPROVED": VERDICT_COLOR_OK,
    "BROKEN": VERDICT_COLOR_FAIL,
    "VULNERABLE": VERDICT_COLOR_FAIL,
    "RED": VERDICT_COLOR_FAIL,
    "PENDING": VERDICT_COLOR_PENDING,
    "SKIPPED": VERDICT_COLOR_PENDING,
    "PARTIAL": VERDICT_COLOR_PENDING,
}


def color_for_verdict(verdict: str) -> str:
    """Return token color for a verdict string."""
    return _VERDICT_COLOR_MAP.get(verdict, "#6b7280")
