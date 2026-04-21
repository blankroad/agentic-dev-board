from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def test_brainstorm_skill_calls_save_brainstorm():
    """Brainstorm SKILL.md must instruct Claude to call agentboard_save_brainstorm."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    assert "agentboard_save_brainstorm" in content, (
        "brainstorm SKILL.md must include agentboard_save_brainstorm MCP call"
    )


def test_gauntlet_skill_requires_approve_before_lock():
    """Gauntlet SKILL.md must instruct Claude to call agentboard_approve_plan before lock_plan."""
    skill_md = SKILLS_DIR / "agentboard-gauntlet" / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    assert "agentboard_approve_plan" in content, (
        "gauntlet SKILL.md must document the approval step before agentboard_lock_plan"
    )


# ── s_001: updated frontmatter description ────────────────────────────────────

def test_brainstorm_frontmatter_references_3_phase():
    """s_001: SKILL.md frontmatter description must reference 3-Phase structure, not old 5-question style."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "5 clarifying questions" not in content, (
        "frontmatter still references the old '5 clarifying questions' behavior"
    )
    assert "Phase" in content, (
        "frontmatter or body must reference Phase structure"
    )


# ── s_002: preamble with agentboard_list_goals + Grep ───────────────────────────

def test_brainstorm_preamble_has_list_goals_and_grep():
    """s_002: SKILL.md must instruct Claude to call agentboard_list_goals and run Grep in preamble."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "agentboard_list_goals" in content, (
        "SKILL.md preamble must include agentboard_list_goals() call"
    )
    assert "Grep" in content or "grep" in content.lower(), (
        "SKILL.md preamble must instruct Grep for existing code discovery"
    )


# ── s_003: Phase 1 has Q1/Q2/Q3 with correct MCP parameter intent ─────────────

def test_brainstorm_phase1_has_direction_validation_questions():
    """s_003: Phase 1 must contain direction-validation questions mapped to premises/risks."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "Phase 1" in content, "Phase 1 block missing"
    assert "premises" in content, "Q1→premises mapping missing"
    assert "risks" in content, "Q3→risks mapping missing"
    assert "existing_code_notes" in content, "Q2→existing_code_notes mapping missing"


# ── s_004: STOP marker after Phase 1 ─────────────────────────────────────────

def test_brainstorm_stop_marker_after_phase1():
    """s_004 (v2 — 6-phase rewrite, goal g_20260421_041017_af7f7a):
    Phase 1 must end with an explicit branching instruction that directs
    the reader to Phase 2 (CLEAR) or to Phase 3 (multi-request). The
    legacy literal 'STOP' marker was an artifact of the old Q1-Q4 flow
    — deterministic branching wording replaces it.

    SCOPE: this relaxation applies ONLY to the brainstorm SKILL.md.
    Other skill files that use literal 'STOP' as a reviewer-halt
    semaphore (if any) are unaffected — their tests live elsewhere and
    are not modified by this goal.
    """
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    phase1_idx = content.find("## Phase 1")
    phase2_idx = content.find("## Phase 2")
    assert phase1_idx != -1, "## Phase 1 section header missing"
    assert phase2_idx != -1, "## Phase 2 section header missing"
    phase1_block = content[phase1_idx:phase2_idx]
    # Either the literal STOP marker (legacy) OR the new explicit branch
    # instruction ("proceed to Phase 2" / "Phase 3 adaptive") must appear.
    allowed = ["STOP", "proceed to Phase 2", "proceed to Phase 3", "Phase 2 CLEAR Fast-Path check", "Phase 3 adaptive loop"]
    assert any(k in phase1_block for k in allowed), (
        f"Phase 1 must end with an explicit branch instruction; "
        f"none of {allowed} found in the Phase 1 block"
    )


# ── s_005: Phase 2 MANDATORY with ≥2 alternatives + RECOMMENDATION ────────────

def test_brainstorm_phase2_mandatory_with_recommendation():
    """s_005: Phase 2 must be MANDATORY and include RECOMMENDATION."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "Phase 2" in content, "Phase 2 block missing"
    assert "MANDATORY" in content, "Phase 2 must be labeled MANDATORY"
    assert "RECOMMENDATION" in content, "Phase 2 must include RECOMMENDATION output"


# ── s_006: STOP marker after Phase 2 ─────────────────────────────────────────

def test_brainstorm_stop_marker_after_phase2():
    """s_006 (v2 — 6-phase rewrite): Phase 2 CLEAR Fast-Path must end with
    an explicit 'Skip to Phase 4' or 'proceed to Phase 3' branching line
    so Claude does not silently interrogate when CLEAR was available (or
    vice versa). Literal 'STOP' marker is no longer required."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    phase2_idx = content.find("## Phase 2")
    phase3_idx = content.find("## Phase 3")
    assert phase2_idx != -1, "## Phase 2 section header missing"
    assert phase3_idx != -1, "## Phase 3 section header missing"
    phase2_block = content[phase2_idx:phase3_idx]
    allowed = ["STOP", "Skip to Phase 4", "proceed to Phase 3", "proceed to Phase 4"]
    assert any(k in phase2_block for k in allowed), (
        f"Phase 2 must end with an explicit branch instruction; "
        f"none of {allowed} found in the Phase 2 block"
    )


# ── s_007: Phase 3 MCP call correct mapping ───────────────────────────────────

def test_brainstorm_phase3_mcp_mapping_correct():
    """s_007: Phase 3 agentboard_save_brainstorm call must include all required parameters."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
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
    """s_008: Phase 3 must invoke agentboard-gauntlet and handle user decline gracefully."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    phase3_idx = content.find("## Phase 3")
    phase3_body = content[phase3_idx:]
    assert "agentboard-gauntlet" in phase3_body, (
        "Phase 3 must instruct handoff to agentboard-gauntlet"
    )
    # Check decline path exists somewhere after Phase 3
    assert "decline" in phase3_body.lower() or "거부" in phase3_body or "지금은" in phase3_body, (
        "Phase 3 must handle user declining the gauntlet handoff"
    )


# ── s_009: CLEAR fast-path preserved ─────────────────────────────────────────

def test_brainstorm_clear_fastpath_preserved():
    """s_009: CLEAR fast-path must be preserved for already-specific goals."""
    skill_md = SKILLS_DIR / "agentboard-brainstorm" / "SKILL.md"
    content = skill_md.read_text()
    assert "CLEAR" in content, (
        "CLEAR fast-path must be preserved for specific goals"
    )


GAUNTLET_DIR = SKILLS_DIR / "agentboard-gauntlet"


# ── g_001: bad example in atomic_steps guidance ───────────────────────────────

def test_gauntlet_bad_example_present():
    """g_001: atomic_steps guidance must contain a bad example (counter-example)."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    guidance_idx = content.find("## atomic_steps guidance")
    assert guidance_idx != -1, "atomic_steps guidance section missing"
    guidance_body = content[guidance_idx:]
    assert "Bad:" in guidance_body or "❌" in guidance_body, (
        "atomic_steps guidance must contain a bad example (Bad: or ❌)"
    )


# ── g_002: good counter-example in atomic_steps guidance ─────────────────────

def test_gauntlet_good_example_present():
    """g_002: atomic_steps guidance must contain a good counter-example."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    guidance_idx = content.find("## atomic_steps guidance")
    assert guidance_idx != -1, "atomic_steps guidance section missing"
    guidance_body = content[guidance_idx:]
    assert "Good:" in guidance_body or "✅" in guidance_body, (
        "atomic_steps guidance must contain a good counter-example (Good: or ✅)"
    )


# ── g_003: step splitter trigger ─────────────────────────────────────────────

def test_gauntlet_step_splitter_trigger():
    """g_003: atomic_steps guidance must document the splitter trigger."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    guidance_idx = content.find("## atomic_steps guidance")
    assert guidance_idx != -1, "atomic_steps guidance section missing"
    guidance_body = content[guidance_idx:]
    assert "splitter" in guidance_body.lower() or (
        '"and"' in guidance_body and "split" in guidance_body.lower()
    ), (
        "atomic_steps guidance must document step splitter trigger (split on 'and')"
    )


# ── g_004: Step Quality Review section after Decide ──────────────────────────

def test_gauntlet_step_quality_review_section():
    """g_004: Step Quality Review section must exist after Decide section."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    decide_idx = content.find("## Step 5 — Decide")
    review_idx = content.find("## Step Quality Review")
    assert decide_idx != -1, "## Step 5 — Decide section missing"
    assert review_idx != -1, "## Step Quality Review section missing"
    assert decide_idx < review_idx, (
        "## Step Quality Review must appear after ## Step 5 — Decide"
    )


# ── g_005: Step Quality Review OK and warning notation ───────────────────────

def test_gauntlet_step_review_has_ok_and_warning():
    """g_005: Step Quality Review section must reference OK and warning notation."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    review_idx = content.find("## Step Quality Review")
    assert review_idx != -1, "## Step Quality Review section missing"
    review_body = content[review_idx:]
    assert "OK" in review_body, "Step Quality Review must contain OK notation"
    assert "warning" in review_body.lower() or "⚠" in review_body, (
        "Step Quality Review must contain warning notation"
    )


# ── g_006: Step Quality Review proceed to lock ───────────────────────────────

def test_gauntlet_step_review_proceed_to_lock():
    """g_006: Step Quality Review must contain 'proceed to lock' instruction."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    review_idx = content.find("## Step Quality Review")
    assert review_idx != -1, "## Step Quality Review section missing"
    review_body = content[review_idx:]
    assert "proceed to lock" in review_body.lower(), (
        "Step Quality Review all-clear path must contain 'proceed to lock'"
    )


# ── sr_001: Single Responsibility rule in Step 3 ─────────────────────────────

def test_gauntlet_arch_single_responsibility_rule():
    """sr_001: Step 3 Architecture section must contain Single Responsibility rule."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    step3_idx = content.find("## Step 3 — Architecture")
    step4_idx = content.find("## Step 4 — Challenge")
    assert step3_idx != -1, "## Step 3 — Architecture section missing"
    assert step4_idx != -1, "## Step 4 — Challenge section missing"
    step3_body = content[step3_idx:step4_idx]
    assert "Single Responsibility" in step3_body, (
        "Step 3 Architecture section must contain Single Responsibility rule"
    )


# ── sr_002: bad example in Critical Files guidance ───────────────────────────

def test_gauntlet_arch_critical_files_bad_example():
    """sr_002: Step 3 Critical Files guidance must contain a bad example."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    step3_idx = content.find("## Step 3 — Architecture")
    step4_idx = content.find("## Step 4 — Challenge")
    step3_body = content[step3_idx:step4_idx]
    assert "Bad:" in step3_body or "❌" in step3_body, (
        "Step 3 Critical Files guidance must contain a bad example (Bad: or ❌)"
    )


# ── sr_003: good example in Critical Files guidance ──────────────────────────

def test_gauntlet_arch_critical_files_good_example():
    """sr_003: Step 3 Critical Files guidance must contain a good example."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    step3_idx = content.find("## Step 3 — Architecture")
    step4_idx = content.find("## Step 4 — Challenge")
    step3_body = content[step3_idx:step4_idx]
    assert "Good:" in step3_body or "✅" in step3_body, (
        "Step 3 Critical Files guidance must contain a good example (Good: or ✅)"
    )


# ── sr_004: out_of_scope_guard intent annotation pattern ─────────────────────

def test_gauntlet_out_of_scope_guard_intent_annotation():
    """sr_004: Out-of-scope Guard guidance must contain intent annotation pattern."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    step3_idx = content.find("## Step 3 — Architecture")
    step4_idx = content.find("## Step 4 — Challenge")
    step3_body = content[step3_idx:step4_idx]
    assert "out_of_scope_guard" in step3_body, "out_of_scope_guard example missing from Step 3"
    assert " — " in step3_body, (
        "out_of_scope_guard must show intent annotation pattern (path — intent)"
    )


# ── P1-1b: task metadata markers for CSO / redteam entry ────────────────────

def test_gauntlet_finalize_sets_task_metadata():
    """Finalize must set production_destined and security_sensitive_plan via update_task_status."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    finalize_idx = content.find("## Finalize")
    handoff_idx = content.find("## Handoff")
    body = content[finalize_idx:handoff_idx]
    assert "agentboard_update_task_status" in body, "Finalize must call update_task_status"
    assert "production_destined" in body, "Finalize must set production_destined marker"
    assert "security_sensitive_plan" in body, "Finalize must set security_sensitive_plan marker"
    assert "agentboard_check_security_sensitive" in body, (
        "Finalize must call check_security_sensitive on plan text"
    )


def test_cso_preamble_reads_task_metadata():
    """CSO must check task.metadata.security_sensitive_plan to decide auto-entry."""
    skill_md = SKILLS_DIR / "agentboard-cso" / "SKILL.md"
    content = skill_md.read_text()
    assert "task.metadata" in content or "metadata" in content, (
        "CSO must reference task metadata"
    )
    assert "security_sensitive_plan" in content, (
        "CSO must check security_sensitive_plan marker"
    )


def test_redteam_preamble_reads_task_metadata():
    """Redteam must check task.metadata.production_destined to decide auto-entry."""
    skill_md = SKILLS_DIR / "agentboard-redteam" / "SKILL.md"
    content = skill_md.read_text()
    assert "production_destined" in content, (
        "Redteam must check production_destined marker"
    )


# ── P1-3: integration_test_command (smoke gate) ─────────────────────────────

def test_gauntlet_documents_integration_test_command():
    """Gauntlet SKILL must reference integration_test_command in Decide schema."""
    skill_md = GAUNTLET_DIR / "SKILL.md"
    content = skill_md.read_text()
    assert "integration_test_command" in content, (
        "Gauntlet must document integration_test_command field"
    )


def test_approval_documents_smoke_gate():
    """Approval SKILL must describe smoke gate with integration_test_command."""
    skill_md = SKILLS_DIR / "agentboard-approval" / "SKILL.md"
    content = skill_md.read_text()
    assert "integration_test_command" in content, (
        "Approval must document integration_test_command gate"
    )


# ── P1-2b: dep-audit skill + approval CVE gate ──────────────────────────────

def test_dep_audit_skill_exists_with_frontmatter():
    skill_md = SKILLS_DIR / "agentboard-dep-audit" / "SKILL.md"
    assert skill_md.exists(), "agentboard-dep-audit skill must exist"
    content = skill_md.read_text()
    assert "name: agentboard-dep-audit" in content
    assert "agentboard_check_dependencies" in content, (
        "Skill must call agentboard_check_dependencies"
    )


def test_approval_documents_dep_audit_gate():
    skill_md = SKILLS_DIR / "agentboard-approval" / "SKILL.md"
    content = skill_md.read_text()
    assert "agentboard_check_dependencies" in content, (
        "Approval must invoke dep audit tool"
    )


# ── P1-5: retro auto-proposes learnings ─────────────────────────────────────

def test_retro_skill_documents_learning_proposals():
    skill_md = SKILLS_DIR / "agentboard-retro" / "SKILL.md"
    content = skill_md.read_text()
    assert "learning_proposals" in content, (
        "Retro skill must document the learning_proposals field"
    )
    assert "agentboard_save_learning" in content, (
        "Retro skill must describe save_learning invocation for proposals"
    )
