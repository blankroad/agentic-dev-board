"""Verify agentboard-gauntlet SKILL.md sets task.metadata.ui_surface."""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "agentboard-gauntlet"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL_PATH.read_text()


def test_gauntlet_sets_ui_surface_metadata() -> None:
    """# guards: edge-case-red-rule
    edge: integration wiring — gauntlet must set ui_surface on task metadata."""
    assert "ui_surface" in _text()


def test_gauntlet_describes_ui_keyword_detection() -> None:
    """Gauntlet must document the keyword set it scans for."""
    text = _text().lower()
    # at least 3 of the 7 canonical keywords must be named
    hits = sum(kw in text for kw in ("tui", "textual", "widget", "pilot", "browser", "ui", "frontend"))
    assert hits >= 3, f"gauntlet doc doesn't enumerate UI keywords: {hits} hit(s)"
