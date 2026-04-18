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
