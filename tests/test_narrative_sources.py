"""Unit tests for src/agentboard/narrative/sources.py — pure readers that
parse .devboard artifacts into dataclasses carrying source-citation
metadata. See goal g_20260420_032908_54200a."""

from __future__ import annotations

import json
from pathlib import Path


def test_parse_plan_sections_extracts_problem_from_canonical_plan(tmp_path: Path) -> None:
    """Happy-path: a plan.md with all canonical H2 sections yields a
    PlanSections whose `problem` field holds the raw Problem-section text."""
    from agentboard.narrative.sources import parse_plan_sections

    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nlocked_hash: abc\n---\n\n"
        "## Problem\n\nThe cockpit had no instruments.\n\n"
        "## Architecture\n\nThree-pane layout.\n\n"
        "## Scope Decision\n\nHOLD\n\n"
        "## Budget\n\n- token_ceiling: 150000\n",
        encoding="utf-8",
    )

    sections = parse_plan_sections(plan)

    assert "The cockpit had no instruments." in sections.problem, (
        f"problem section missing expected text, got {sections.problem!r}"
    )


def test_parse_plan_sections_reports_missing_sections(tmp_path: Path) -> None:
    """A plan.md missing one canonical H2 section surfaces it in
    `missing_sections` so the generator can flag partial coverage in
    the output's metadata line."""
    from agentboard.narrative.sources import parse_plan_sections

    plan = tmp_path / "plan.md"
    plan.write_text(
        "## Problem\n\nX\n\n"
        "## Architecture\n\nY\n\n"
        "## Scope Decision\n\nHOLD\n",
        encoding="utf-8",
    )

    sections = parse_plan_sections(plan)

    assert sections.missing_sections == ["Budget"], (
        f"expected missing=['Budget'], got {sections.missing_sections!r}"
    )


def test_group_decisions_by_iter_tolerates_missing_fields(tmp_path: Path) -> None:
    """Older decisions.jsonl rows may omit `verdict_source`. The reader
    must coerce the missing value to '?' rather than raise KeyError."""
    from agentboard.narrative.sources import group_decisions_by_iter

    jsonl = tmp_path / "decisions.jsonl"
    jsonl.write_text(
        # row missing verdict_source entirely
        '{"iter": 1, "phase": "tdd_red", "reasoning": "stub"}\n'
        # row with full shape
        '{"iter": 2, "phase": "tdd_green", "reasoning": "ok",'
        ' "verdict_source": "GREEN_CONFIRMED"}\n',
        encoding="utf-8",
    )

    groups = group_decisions_by_iter(jsonl)

    assert 1 in groups and groups[1][0].get("verdict_source") == "?", (
        f"missing verdict_source should coerce to '?', got {groups!r}"
    )
    assert groups[2][0].get("verdict_source") == "GREEN_CONFIRMED"
