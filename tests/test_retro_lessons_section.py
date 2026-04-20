"""Verify agentboard-retro SKILL.md instructs the Lessons upsert step."""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "agentboard-retro"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL_PATH.read_text()


def test_retro_mentions_upsert_plan_section() -> None:
    """# guards: edge-case-red-rule
    edge: integration wiring — skill must actually call the helper."""
    assert "upsert_plan_section" in _text()


def test_retro_mentions_plan_section_lessons() -> None:
    assert "PlanSection.LESSONS" in _text()


def test_retro_mentions_per_goal_iteration() -> None:
    """Retro can cover multiple goals → must instruct per-goal loop."""
    text = _text().lower()
    # at least one of these phrases — implementation author's choice
    assert ("per goal" in text or "per-goal" in text or "for each goal" in text)


def test_retro_mentions_empty_learnings_skip() -> None:
    """# guards: edge-case-red-rule
    edge: empty input — goal with zero applicable learnings should not
    produce an empty Lessons section."""
    text = _text().lower()
    assert "skip" in text or "no lessons" in text or "zero" in text
