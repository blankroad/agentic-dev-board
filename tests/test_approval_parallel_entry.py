"""Tests that SKILL.md contracts are wired for the parallel-review flow."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPROVAL_MD = ROOT / "skills" / "agentboard-approval" / "SKILL.md"
TDD_MD = ROOT / "skills" / "agentboard-tdd" / "SKILL.md"
PARALLEL_MD = ROOT / "skills" / "agentboard-parallel-review" / "SKILL.md"


def test_approval_recognizes_parallel_review_entry() -> None:
    """Approval Step 0 must name 'parallel_review' as the 1st-priority entry to accept."""
    text = APPROVAL_MD.read_text(encoding="utf-8")
    assert "parallel_review" in text, "approval SKILL.md does not mention parallel_review entry"
    # Must explicitly prioritize parallel_review over separate cso+redteam entries
    assert "priority" in text.lower() or "1순위" in text or "우선" in text, (
        "approval SKILL.md must say parallel_review entry is preferred / higher priority"
    )


def test_approval_falls_back_to_legacy_cso_redteam() -> None:
    """Approval must document the legacy fallback: no parallel_review → accept phase=cso + phase=redteam pair."""
    text = APPROVAL_MD.read_text(encoding="utf-8")
    assert "legacy" in text.lower() or "fallback" in text.lower(), (
        "approval SKILL.md must mention the legacy cso+redteam fallback"
    )
    assert 'phase="cso"' in text or "phase='cso'" in text, "approval SKILL.md must reference phase=cso for fallback"
    assert 'phase="redteam"' in text or "phase='redteam'" in text, "approval SKILL.md must reference phase=redteam for fallback"


def test_tdd_handoff_points_to_parallel_review() -> None:
    """TDD SKILL.md's handoff section must mention agentboard-parallel-review (for reviewer PASS flow)."""
    text = TDD_MD.read_text(encoding="utf-8")
    assert "agentboard-parallel-review" in text, (
        "tdd SKILL.md handoff does not point to agentboard-parallel-review"
    )


def test_parallel_review_skill_contains_agent_dispatch() -> None:
    """The parallel-review SKILL.md file must exist and instruct Agent-tool parallel dispatch."""
    assert PARALLEL_MD.exists(), f"missing: {PARALLEL_MD}"
    text = PARALLEL_MD.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "agent" in lowered, "parallel-review SKILL.md must mention the Agent tool"
    assert "parallel" in lowered or "dispatch" in lowered, (
        "parallel-review SKILL.md must describe parallel dispatch"
    )
    assert "devboard_log_parallel_review" in text, (
        "parallel-review SKILL.md must reference the devboard_log_parallel_review MCP tool"
    )
