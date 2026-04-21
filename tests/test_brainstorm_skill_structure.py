"""Structural assertions for skills/agentboard-brainstorm/SKILL.md.

This is a markdown-file audit — no subprocess, no textual, no MCP.
Just read the source SKILL.md and assert on substrings.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO / "skills" / "agentboard-brainstorm" / "SKILL.md"


def _read() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_six_phase_structure_present() -> None:
    """s_002 — all 6 phase + MCP/handoff keywords must appear verbatim."""
    text = _read()
    required = [
        "## Phase 0",
        "Request Restatement",
        "CLEAR Fast-Path",
        "Adaptive Clarification",
        "Self-review",
        "devboard_save_brainstorm",
        "agentboard-gauntlet",
    ]
    missing = [k for k in required if k not in text]
    assert not missing, f"required 6-phase keywords missing: {missing}"


def test_adaptive_clarification_has_hard_cap() -> None:
    """s_003 — Phase 3 must declare a hard cap on clarifying questions."""
    text = _read()
    variants = ["cap 3", "cap-3", "hard cap", "maximum 3 questions", "3 questions total"]
    assert any(v in text for v in variants), (
        f"no hard cap on adaptive clarification found; expected one of {variants}"
    )


def test_adaptive_axis_templates_present() -> None:
    """s_004 — at least one axis-specific question template must appear
    so Claude has a concrete example to imitate, not only abstract axes."""
    text = _read()
    templates = ["purpose →", "constraints →", "success →", "wedge →"]
    assert any(t in text for t in templates), (
        f"no axis-specific template; expected one of {templates}"
    )


def test_self_review_has_retry_guard() -> None:
    """s_005 — Phase 5 Self-review must declare a retry cap to avoid
    infinite regenerate loops when a check keeps failing."""
    text = _read()
    phrases = ["retry limit", "retry: 1", "Retry limit", "1회", "loop guard"]
    assert any(p in text for p in phrases), (
        f"self-review retry/loop guard missing; expected one of {phrases}"
    )


def test_frontmatter_preserved() -> None:
    """s_006 — YAML frontmatter with name + description must survive."""
    text = _read()
    assert text.startswith("---\n"), "file must start with YAML frontmatter delimiter"
    head = text.split("\n---\n", 1)[0]
    assert "name: agentboard-brainstorm" in head, "frontmatter name field missing"
    assert "description:" in head, "frontmatter description field missing"


def test_out_of_scope_unchanged() -> None:
    """s_007 — guarded files outside this goal must have no diff vs main."""
    import subprocess

    guarded = [
        "skills/agentboard-gauntlet/SKILL.md",
        "skills/agentboard-tdd/SKILL.md",
        "skills/agentboard-approval/SKILL.md",
        "skills/agentboard-parallel-review/SKILL.md",
        "skills/agentboard-cso/SKILL.md",
        "skills/agentboard-redteam/SKILL.md",
        "skills/agentboard-rca/SKILL.md",
        "skills/agentboard-eng-review/SKILL.md",
        "skills/agentboard-synthesize-report/SKILL.md",
        "skills/agentboard-replay/SKILL.md",
        "skills/agentboard-retro/SKILL.md",
        "skills/agentboard-ui-preview/SKILL.md",
        "skills/agentboard-dep-audit/SKILL.md",
    ]
    # Also guard: nothing in src/ changed
    src_paths = ["src/devboard"]
    offenders: list[str] = []
    for base in ("main", "origin/main"):
        proc = subprocess.run(
            ["git", "-C", str(REPO), "diff", base, "--", *guarded, *src_paths],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            if proc.stdout:
                for line in proc.stdout.splitlines():
                    if line.startswith("diff --git a/"):
                        offenders.append(line.split()[2].removeprefix("a/"))
            break
    else:
        import pytest as _pytest
        _pytest.skip("no main/origin/main baseline available")
    assert not offenders, (
        f"out-of-scope files changed (scope_guard violation): {offenders}"
    )


def test_phase4_mandates_ideal_and_realistic_slots() -> None:
    """Follow-up to goal g_20260421_041017_af7f7a: Phase 4 Alternatives
    must always include two explicit slot labels — `가장 이상적` and
    `현실적` — so downstream readers can compare ambition vs feasibility
    on every brainstorm. User directive: `가장 이상적인 방안은 반드시
    있어야함`."""
    text = _read()
    phase4_idx = text.find("## Phase 4")
    phase5_idx = text.find("## Phase 5")
    assert phase4_idx != -1 and phase5_idx != -1, (
        "Phase 4 / Phase 5 section headers missing"
    )
    phase4_block = text[phase4_idx:phase5_idx]
    # Both Korean labels MUST appear inside the Phase 4 block.
    assert "가장 이상적" in phase4_block, (
        "Phase 4 must name a '가장 이상적' (most-ideal) slot as mandatory. "
        f"Phase 4 block:\n{phase4_block[:600]}"
    )
    assert "현실적" in phase4_block, (
        "Phase 4 must name a '현실적' (realistic) slot as mandatory. "
        f"Phase 4 block:\n{phase4_block[:600]}"
    )
    # Mandatoriness must be explicit, not just a suggestion.
    assert any(tok in phase4_block for tok in ("MANDATORY", "필수", "무조건")), (
        "Phase 4 must mark the two slots as mandatory (MANDATORY / 필수 / 무조건)"
    )


def test_gstack_jargon_removed() -> None:
    """s_001 — the gstack/YC-pitch terms that motivated this rewrite must
    be gone from the body. These phrases were ambient in the previous
    template and produce low-signal questions for internal dev tools."""
    text = _read()
    forbidden = [
        "Desperate Specificity",
        "Demand Reality",
        "Real Users",
        "nice-to-have",
        "Q1: Real Users",
        "Q3: Demand Reality",
    ]
    leaked = [k for k in forbidden if k in text]
    assert not leaked, (
        f"gstack jargon still present in SKILL.md: {leaked}"
    )
