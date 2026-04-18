from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def test_brainstorm_skill_calls_save_brainstorm():
    """Brainstorm SKILL.md must instruct Claude to call devboard_save_brainstorm."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    assert "devboard_save_brainstorm" in content, (
        "brainstorm SKILL.md must include devboard_save_brainstorm MCP call"
    )


def test_gauntlet_skill_requires_approve_before_lock():
    """Gauntlet SKILL.md must instruct Claude to call devboard_approve_plan before lock_plan."""
    skill_md = SKILLS_DIR / "devboard-gauntlet" / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    assert "devboard_approve_plan" in content, (
        "gauntlet SKILL.md must document the approval step before devboard_lock_plan"
    )


# ── s_001: updated frontmatter description ────────────────────────────────────

def test_brainstorm_frontmatter_references_3_phase():
    """s_001: SKILL.md frontmatter description must reference 3-Phase structure, not old 5-question style."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "5 clarifying questions" not in content, (
        "frontmatter still references the old '5 clarifying questions' behavior"
    )
    assert "Phase" in content, (
        "frontmatter or body must reference Phase structure"
    )


# ── s_002: preamble with devboard_list_goals + Grep ───────────────────────────

def test_brainstorm_preamble_has_list_goals_and_grep():
    """s_002: SKILL.md must instruct Claude to call devboard_list_goals and run Grep in preamble."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "devboard_list_goals" in content, (
        "SKILL.md preamble must include devboard_list_goals() call"
    )
    assert "Grep" in content or "grep" in content.lower(), (
        "SKILL.md preamble must instruct Grep for existing code discovery"
    )


# ── s_003: Phase 1 has Q1/Q2/Q3 with correct MCP parameter intent ─────────────

def test_brainstorm_phase1_has_direction_validation_questions():
    """s_003: Phase 1 must contain direction-validation questions mapped to premises/risks."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "Phase 1" in content, "Phase 1 block missing"
    assert "premises" in content, "Q1→premises mapping missing"
    assert "risks" in content, "Q3→risks mapping missing"
    assert "existing_code_notes" in content, "Q2→existing_code_notes mapping missing"


# ── s_004: STOP marker after Phase 1 ─────────────────────────────────────────

def test_brainstorm_stop_marker_after_phase1():
    """s_004: A STOP marker must appear after the Phase 1 section header and before Phase 2 header."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "STOP" in content, "No STOP marker found in SKILL.md"
    # Use section headers (## Phase N) to avoid matching frontmatter text
    phase1_idx = content.find("## Phase 1")
    phase2_idx = content.find("## Phase 2")
    assert phase1_idx != -1, "## Phase 1 section header missing"
    assert phase2_idx != -1, "## Phase 2 section header missing"
    stop_idx = content.find("STOP", phase1_idx)
    assert stop_idx != -1, "No STOP marker found after ## Phase 1 header"
    assert phase1_idx < stop_idx < phase2_idx, (
        "STOP marker must appear between ## Phase 1 and ## Phase 2 headers"
    )


# ── s_005: Phase 2 MANDATORY with ≥2 alternatives + RECOMMENDATION ────────────

def test_brainstorm_phase2_mandatory_with_recommendation():
    """s_005: Phase 2 must be MANDATORY and include RECOMMENDATION."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "Phase 2" in content, "Phase 2 block missing"
    assert "MANDATORY" in content, "Phase 2 must be labeled MANDATORY"
    assert "RECOMMENDATION" in content, "Phase 2 must include RECOMMENDATION output"


# ── s_006: STOP marker after Phase 2 ─────────────────────────────────────────

def test_brainstorm_stop_marker_after_phase2():
    """s_006: A second STOP marker must appear after the Phase 2 section header and before Phase 3."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    phase2_idx = content.find("## Phase 2")
    phase3_idx = content.find("## Phase 3")
    assert phase2_idx != -1, "## Phase 2 section header missing"
    assert phase3_idx != -1, "## Phase 3 section header missing"
    stop_after_p2 = content.find("STOP", phase2_idx)
    assert stop_after_p2 != -1 and stop_after_p2 < phase3_idx, (
        "STOP marker must appear between ## Phase 2 and ## Phase 3 headers"
    )


# ── s_007: Phase 3 MCP call correct mapping ───────────────────────────────────

def test_brainstorm_phase3_mcp_mapping_correct():
    """s_007: Phase 3 devboard_save_brainstorm call must include all required parameters."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "## Phase 3" in content, "## Phase 3 section header missing"
    phase3_idx = content.find("## Phase 3")
    phase3_body = content[phase3_idx:]
    assert "premises" in phase3_body, "Phase 3 must reference premises parameter"
    assert "risks" in phase3_body, "Phase 3 must reference risks parameter"
    assert "alternatives" in phase3_body, "Phase 3 must reference alternatives parameter"
    assert "existing_code_notes" in phase3_body, "Phase 3 must reference existing_code_notes"


# ── s_008: Phase 3 gauntlet handoff + decline path ───────────────────────────

def test_brainstorm_phase3_gauntlet_handoff_and_decline():
    """s_008: Phase 3 must invoke devboard-gauntlet and handle user decline gracefully."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    phase3_idx = content.find("## Phase 3")
    phase3_body = content[phase3_idx:]
    assert "devboard-gauntlet" in phase3_body, (
        "Phase 3 must instruct handoff to devboard-gauntlet"
    )
    # Check decline path exists somewhere after Phase 3
    assert "decline" in phase3_body.lower() or "거부" in phase3_body or "지금은" in phase3_body, (
        "Phase 3 must handle user declining the gauntlet handoff"
    )


# ── s_009: CLEAR fast-path preserved ─────────────────────────────────────────

def test_brainstorm_clear_fastpath_preserved():
    """s_009: CLEAR fast-path must be preserved for already-specific goals."""
    skill_md = SKILLS_DIR / "devboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "CLEAR" in content, (
        "CLEAR fast-path must be preserved for specific goals"
    )
