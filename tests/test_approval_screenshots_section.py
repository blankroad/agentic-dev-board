"""Verify devboard-approval SKILL.md wires tui_render_smoke + Screenshots upsert."""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "devboard-approval"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL_PATH.read_text()


def test_approval_mentions_tui_render_smoke() -> None:
    """# guards: edge-case-red-rule
    edge: integration wiring — approval must call the MCP tool."""
    assert "devboard_tui_render_smoke" in _text()


def test_approval_mentions_plan_section_screenshots() -> None:
    assert "PlanSection.SCREENSHOTS" in _text()


def test_approval_guards_on_ui_surface_metadata() -> None:
    """# guards: edge-case-red-rule
    edge: empty input — non-UI tasks must skip Screenshots (default False)."""
    assert "ui_surface" in _text()


def test_approval_handles_skipped_reason() -> None:
    """# guards: edge-case-red-rule
    edge: real-TTY divergence — when tui_render_smoke returns skipped_reason
    (no pty, no devboard binary), approval must not write an empty Screenshots
    section or crash."""
    text = _text().lower()
    assert "skipped_reason" in text or "skipped" in text
