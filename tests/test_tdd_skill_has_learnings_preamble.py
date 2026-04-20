"""Verify agentboard-tdd SKILL.md exposes the Learnings Preamble (axis 1).

These are plain-text assertions on the skill markdown. They fail if the
preamble isn't present or if the original Project Guard / Iron Law /
RED-GREEN-REFACTOR structure is disturbed by the edit.
"""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "agentboard-tdd"
    / "SKILL.md"
)


def _skill_text() -> str:
    return SKILL_PATH.read_text()


def test_skill_contains_learnings_preamble_heading() -> None:
    assert "## Learnings Preamble" in _skill_text()


def test_preamble_mentions_devboard_relevant_learnings() -> None:
    assert "devboard_relevant_learnings" in _skill_text()


def test_preamble_mentions_devboard_search_learnings() -> None:
    assert "devboard_search_learnings" in _skill_text()


def test_preamble_uses_preemptive_defense_checklist_term() -> None:
    assert "Preemptive Defense Checklist" in _skill_text()


def test_preamble_caps_top_n_learnings() -> None:
    text = _skill_text()
    # Cap rule: "top N=5" and "200자" (or "200 chars") must appear
    assert "top N=5" in text or "top 5" in text.lower()
    assert "200" in text


def test_preamble_handles_empty_learnings() -> None:
    assert "No prior learnings" in _skill_text()


def test_preamble_requires_guards_tag() -> None:
    text = _skill_text()
    assert "# guards:" in text or "`guards:" in text


def test_project_guard_section_retained() -> None:
    assert "Project Guard" in _skill_text()


def test_iron_law_section_retained() -> None:
    assert "Iron Law" in _skill_text()
