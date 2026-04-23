"""Post-T5 skill-structure tests. Legacy tests targeting the deleted
agentboard-brainstorm / -gauntlet / -tdd skills were removed on T5.
This file keeps the policy-level assertions that still apply to the
active D1 phase skills + post-chain skills (cso, redteam, approval,
dep-audit, retro, lock)."""
from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


# ── CSO / redteam read task metadata ───────────────────────────────────────

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


# ── integration_test_command (smoke gate) — moved from gauntlet to lock (D3) ──

def test_lock_documents_integration_test_command():
    """Lock SKILL must reference integration_test_command in Decide schema
    (ownership moved here from the deprecated gauntlet skill at D3 cutover)."""
    skill_md = SKILLS_DIR / "agentboard-lock" / "SKILL.md"
    content = skill_md.read_text()
    assert "integration_test_command" in content, (
        "Lock must document integration_test_command field"
    )


def test_approval_documents_smoke_gate():
    """Approval SKILL must describe smoke gate with integration_test_command."""
    skill_md = SKILLS_DIR / "agentboard-approval" / "SKILL.md"
    content = skill_md.read_text()
    assert "integration_test_command" in content, (
        "Approval must document integration_test_command gate"
    )


# ── dep-audit skill + approval CVE gate ─────────────────────────────────────

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


# ── retro auto-proposes learnings ──────────────────────────────────────────

def test_retro_skill_documents_learning_proposals():
    skill_md = SKILLS_DIR / "agentboard-retro" / "SKILL.md"
    content = skill_md.read_text()
    assert "learning_proposals" in content, (
        "Retro skill must document the learning_proposals field"
    )
    assert "agentboard_save_learning" in content, (
        "Retro skill must describe save_learning invocation for proposals"
    )


# ── D1 chain orchestrator + phase skills present ───────────────────────────

def test_d1_chain_skills_present():
    """Post-T5 expected D1 chain — orchestrator + 6 phase skills."""
    for name in (
        "agentboard-plan",
        "agentboard-intent",
        "agentboard-frame",
        "agentboard-architecture",
        "agentboard-stress",
        "agentboard-lock",
        "agentboard-execute",
    ):
        skill_md = SKILLS_DIR / name / "SKILL.md"
        assert skill_md.exists(), f"D1 chain skill missing: {name}"
        content = skill_md.read_text()
        assert f"name: {name}" in content
