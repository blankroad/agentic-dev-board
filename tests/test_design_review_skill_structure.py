"""Structural assertions for skills/agentboard-design-review/SKILL.md.

Substring-level audit — no subprocess, no textual, no MCP. Just read
the source SKILL.md and assert on substrings / keywords.

The design-review skill is an advisory Claude-Code skill: the tests
here prove the written contract is present. Behavioral enforcement is
out of scope — see learning `skill-contracts-are-advisory-not-runtime`.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "agentboard-design-review"
SKILL_PATH = SKILL_DIR / "SKILL.md"
INSTALLED_SKILL_PATH = (
    REPO / ".claude" / "skills" / "agentboard-design-review" / "SKILL.md"
)
GAUNTLET_SOURCE = REPO / "skills" / "agentboard-gauntlet" / "SKILL.md"
GAUNTLET_INSTALLED = REPO / ".claude" / "skills" / "agentboard-gauntlet" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_skill_file_exists_with_frontmatter() -> None:
    """s_001 — SKILL.md must exist and start with YAML frontmatter that
    names the skill and carries a description."""
    assert SKILL_PATH.exists(), f"expected skill file at {SKILL_PATH}"
    text = _read(SKILL_PATH)
    assert text.startswith("---\n"), "file must start with YAML frontmatter delimiter"
    head = text.split("\n---\n", 1)[0]
    assert "name: agentboard-design-review" in head, "frontmatter name field missing"
    assert "description:" in head, "frontmatter description field missing"


def test_seven_rubric_passes_present() -> None:
    """s_002 — all 7 rubric-pass keywords must appear in the body so the
    skill exposes the full gstack-ported coverage."""
    text = _read(SKILL_PATH)
    required = [
        "Information Architecture",
        "Interaction State Coverage",
        "User Journey",
        "AI Slop Risk",
        "Design System Alignment",
        "Responsive",
        "Unresolved",
    ]
    missing = [k for k in required if k not in text]
    assert not missing, f"rubric pass keywords missing: {missing}"


def test_modal_and_focus_coverage_mandated() -> None:
    """s_003 — the skill must explicitly name the modal-stacking / z-order /
    focus-trap class of UX bug somewhere in the body, because that is the
    specific bug category the user flagged when requesting this layer
    ('화면 분할이 모달 뒤에서 일어남')."""
    text = _read(SKILL_PATH)
    keywords = ["modal stacking", "z-order", "focus trap"]
    hits = [k for k in keywords if k in text]
    assert hits, (
        "none of modal stacking / z-order / focus trap keywords found — "
        "Pass 2 coverage must name at least one of them so Claude has a "
        f"concrete anchor. Looked for: {keywords}"
    )


def test_scoring_thresholds_present() -> None:
    """s_004 — the 0-10 scoring scheme and APPROVED / WARN / BLOCKER
    verdicts must be named in the body, including the threshold values
    (≥7 APPROVED, <5 BLOCKER) so downstream behavior is unambiguous."""
    text = _read(SKILL_PATH)
    assert "0-10" in text, "scoring scale '0-10' missing"
    for verdict in ("APPROVED", "WARN", "BLOCKER"):
        assert verdict in text, f"verdict keyword {verdict!r} missing"
    # threshold anchors — at least one unambiguous pair must exist
    threshold_variants = ["≥7", ">= 7", "7 or higher", "<5", "< 5", "below 5"]
    assert any(v in text for v in threshold_variants), (
        f"no numeric threshold anchor found; expected one of {threshold_variants}"
    )


def test_blocker_retry_and_override_present() -> None:
    """s_005 — BLOCKER verdict path must include a retry cap and a user
    override escape hatch (AskUserQuestion + BLOCKER_OVERRIDDEN sentinel),
    otherwise a stubborn skill can stall the gauntlet indefinitely.
    guards: skill-contracts-are-advisory-not-runtime"""
    text = _read(SKILL_PATH)
    retry_variants = ["retry 1", "retry: 1", "retry cap", "one retry", "1 retry"]
    assert any(v in text for v in retry_variants), (
        f"retry cap missing; expected one of {retry_variants}"
    )
    assert "AskUserQuestion" in text, (
        "override path must use AskUserQuestion to surface the escape hatch"
    )
    assert "BLOCKER_OVERRIDDEN" in text, (
        "decisions.jsonl sentinel 'BLOCKER_OVERRIDDEN' must be named so retros "
        "can grep overridden verdicts"
    )


def test_decision_log_handoff_present() -> None:
    """s_006 — the skill must instruct Claude (in a dedicated phase body,
    not just the frontmatter description) to write a decisions.jsonl entry
    with phase='design_review' at exit. Without this sentinel, retros
    cannot prove the skill ran.
    guards: skill-contracts-are-advisory-not-runtime"""
    text = _read(SKILL_PATH)
    # Cut off YAML frontmatter so we only check the executable body
    body = text.split("\n---\n", 1)[1] if "\n---\n" in text else text
    assert "devboard_log_decision" in body, (
        "body (not just frontmatter) must instruct devboard_log_decision"
    )
    # phase label must be the literal 'design_review'
    phase_variants = ['phase="design_review"', "phase='design_review'", "phase=design_review"]
    assert any(v in body for v in phase_variants), (
        f"body must name phase label 'design_review'; expected one of {phase_variants}"
    )
    # Must be framed as a handoff / log step, not incidental mention
    assert any(tok in body for tok in ("Phase 5", "## Handoff", "Log & Handoff", "Log and Handoff")), (
        "a dedicated handoff / log section must exist in the body"
    )


def test_gate_and_idempotent_upsert_present() -> None:
    """s_007 — Phase 0 Gate must name NOT_APPLICABLE as a valid early-exit
    path, and the arch.md upsert must be described as idempotent (replace,
    not append) so re-runs don't duplicate the Design Review section."""
    text = _read(SKILL_PATH)
    body = text.split("\n---\n", 1)[1] if "\n---\n" in text else text
    assert "NOT_APPLICABLE" in body, (
        "Phase 0 Gate must name the NOT_APPLICABLE early-exit path "
        "(e.g. for meta-goals whose deliverable is a prompt doc, not a UI)"
    )
    # idempotent upsert wording must exist — any variant
    idempotent_variants = ["idempotent", "replace, not append", "replace (not append)"]
    assert any(v in body for v in idempotent_variants), (
        f"arch.md upsert must be framed as idempotent replace; "
        f"expected one of {idempotent_variants}"
    )
    # The target section name must be explicit so Claude doesn't invent a variant
    assert "## Design Review" in body, (
        "arch.md upsert target heading '## Design Review' must be literally named"
    )


def test_installed_copy_matches_source() -> None:
    """s_008 — the installed copy under .claude/skills/ must be byte-exact
    to the source. Without this, Claude Code reads a stale version."""
    assert INSTALLED_SKILL_PATH.exists(), (
        f"installed copy missing at {INSTALLED_SKILL_PATH}"
    )
    src_bytes = SKILL_PATH.read_bytes()
    dst_bytes = INSTALLED_SKILL_PATH.read_bytes()
    assert src_bytes == dst_bytes, (
        "installed copy differs from source — run "
        "`cp skills/agentboard-design-review/SKILL.md "
        ".claude/skills/agentboard-design-review/SKILL.md`"
    )


def test_gauntlet_invokes_design_review() -> None:
    """s_009 — gauntlet SKILL.md must mention agentboard-design-review
    near 'Layer 0' wording so Claude invokes the new skill after the ASCII
    mockup confirm and before Challenge. Both source and installed copy."""
    for path in (GAUNTLET_SOURCE, GAUNTLET_INSTALLED):
        assert path.exists(), f"gauntlet skill missing at {path}"
        text = _read(path)
        assert "agentboard-design-review" in text, (
            f"gauntlet SKILL.md at {path} must name agentboard-design-review"
        )
        # invoke wording must live near the UI Preview Layer 0 block
        ui_idx = text.find("UI Preview integration")
        dr_idx = text.find("agentboard-design-review")
        assert ui_idx != -1, f"UI Preview integration section missing in {path}"
        assert abs(dr_idx - ui_idx) < 2000, (
            "design-review invoke is too far from the UI Preview integration "
            "section — consolidate them so Claude reads them together"
        )
    # source and installed must agree byte-for-byte (same sync contract)
    assert GAUNTLET_SOURCE.read_bytes() == GAUNTLET_INSTALLED.read_bytes(), (
        "gauntlet source and installed copy diverge"
    )


def test_out_of_scope_unchanged() -> None:
    """s_010 — guarded files outside this goal must have no diff vs main."""
    import subprocess

    guarded = [
        "skills/agentboard-brainstorm/SKILL.md",
        "skills/agentboard-tdd/SKILL.md",
        "skills/agentboard-cso/SKILL.md",
        "skills/agentboard-redteam/SKILL.md",
        "skills/agentboard-parallel-review/SKILL.md",
        "skills/agentboard-approval/SKILL.md",
        "skills/agentboard-rca/SKILL.md",
        "skills/agentboard-retro/SKILL.md",
        "skills/agentboard-replay/SKILL.md",
        "skills/agentboard-eng-review/SKILL.md",
        "skills/agentboard-synthesize-report/SKILL.md",
        "skills/agentboard-ui-preview/SKILL.md",
        "skills/agentboard-dep-audit/SKILL.md",
        "src/devboard",
        "pyproject.toml",
        ".mcp.json",
    ]
    offenders: list[str] = []
    for base in ("main", "origin/main"):
        proc = subprocess.run(
            ["git", "-C", str(REPO), "diff", base, "--", *guarded],
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
