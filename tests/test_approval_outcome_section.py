"""Verify agentboard-approval SKILL.md instructs the Outcome upsert step."""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "agentboard-approval"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL_PATH.read_text()


def test_approval_mentions_upsert_plan_section() -> None:
    assert "upsert_plan_section" in _text()


def test_approval_mentions_plan_section_outcome() -> None:
    assert "PlanSection.OUTCOME" in _text()


def test_approval_outcome_step_placed_between_push_and_status() -> None:
    """Step must run AFTER agentboard_push_pr success (we know the PR URL
    and commit) and BEFORE agentboard_update_task_status 'pushed' (so the
    doc reflects reality before the task is marked done)."""
    text = _text()
    push = text.find("agentboard_push_pr")
    upsert = text.find("upsert_plan_section")
    status_update = text.find("agentboard_update_task_status")
    assert push != -1 and upsert != -1 and status_update != -1
    assert push < upsert < status_update, (
        f"ordering wrong: push={push} upsert={upsert} status={status_update}"
    )
