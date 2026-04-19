"""Verify devboard-tdd SKILL.md exposes the Edge-Case RED Rule (axis 2)."""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "devboard-tdd"
    / "SKILL.md"
)


def _skill_text() -> str:
    return SKILL_PATH.read_text()


def test_edge_case_rule_heading_present() -> None:
    assert "Edge-Case RED Rule" in _skill_text()


def test_rule_mentions_six_initial_categories() -> None:
    text = _skill_text().lower()
    # 6 initial categories: empty/None, binary, concurrent mutation, cached stale,
    # integration wiring, real-TTY. Each word must appear somewhere in the rule.
    required = [
        "empty",
        "none",
        "binary",
        "concurrent",
        "cached stale",
        "integration",
        "real-tty",
    ]
    missing = [w for w in required if w not in text]
    assert not missing, f"categories missing: {missing}"


def test_rule_enforces_happy_plus_one_edge() -> None:
    text = _skill_text()
    # allow either "happy + 1 edge" or "happy-path + at least 1 edge"
    assert "happy" in text.lower() and (
        "at least 1 edge" in text.lower()
        or "happy + 1 edge" in text.lower()
        or "+ one edge" in text.lower()
    )


def test_rule_requires_edge_in_test_name_or_docstring() -> None:
    text = _skill_text().lower()
    assert "test name" in text or "test function name" in text
    assert "docstring" in text


def test_rule_addresses_yagni() -> None:
    text = _skill_text()
    assert "YAGNI" in text
    assert "known-risk" in text or "known risk" in text


def test_learnings_preamble_retained() -> None:
    assert "## Learnings Preamble" in _skill_text()


def test_iron_law_retained_after_edit() -> None:
    assert "Iron Law" in _skill_text()
