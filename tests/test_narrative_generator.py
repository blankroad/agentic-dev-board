"""Tests for src/devboard/narrative/generator.py — assemblers for the
five narrative sections plus the `generate_narrative` orchestrator that
writes `plan_summary.md` for a goal. See goal g_20260420_032908_54200a."""

from __future__ import annotations

import re
from pathlib import Path


def test_assemble_purpose_emits_source_cited_section() -> None:
    """assemble_purpose wraps PlanSections.problem in an H2 section
    whose body carries a `(source: plan.md ## Problem)` citation."""
    from devboard.narrative.generator import assemble_purpose
    from devboard.narrative.sources import PlanSections

    out = assemble_purpose(PlanSections(problem="The cockpit had no instruments."))

    assert out.startswith("## Purpose\n"), (
        f"section must start with '## Purpose\\n', got {out[:30]!r}"
    )
    assert "(source: plan.md ## Problem)" in out, (
        f"missing per-sentence citation, got body: {out!r}"
    )


def test_assemble_process_lists_redteam_rounds_with_verdicts() -> None:
    """assemble_process scans decisions grouped by iter for redteam
    rows and emits a round-by-round listing with (source: decisions.jsonl
    iter=N phase=redteam) citations."""
    from devboard.narrative.generator import assemble_process

    grouped = {
        8: [{"iter": 8, "phase": "redteam", "reasoning": "Round 1 found TypeError in dispatch.",
             "verdict_source": "BROKEN"}],
        11: [{"iter": 11, "phase": "redteam", "reasoning": "Round 4 only MEDIUM/HIGH; no crash.",
              "verdict_source": "SURVIVED"}],
    }

    out = assemble_process(grouped)

    assert "Round 1 (iter=8) returned BROKEN" in out, (
        f"missing BROKEN round listing: {out!r}"
    )
    assert "Round 2 (iter=11) returned SURVIVED" in out, (
        f"missing SURVIVED round listing: {out!r}"
    )
    assert "(source: decisions.jsonl iter=8" in out
    assert "(source: decisions.jsonl iter=11" in out


def test_generate_narrative_writes_five_section_plan_summary(tmp_path: Path) -> None:
    """generate_narrative on a minimal tmp goal dir writes
    plan_summary.md whose body holds exactly five H2 headers in order:
    ## Purpose, ## Plan, ## Process, ## Result, ## Review."""
    from devboard.narrative.generator import generate_narrative

    goal_id = "g_fixture"
    goal_dir = tmp_path / ".devboard" / "goals" / goal_id
    task_dir = goal_dir / "tasks" / "t_fixture"
    (task_dir / "changes").mkdir(parents=True)
    (goal_dir / "plan.md").write_text(
        "## Problem\n\nP body\n\n"
        "## Architecture\n\nArch body\n\n"
        "## Scope Decision\n\nHOLD\n\n"
        "## Budget\n\n- token_ceiling: 100000\n",
        encoding="utf-8",
    )
    (task_dir / "decisions.jsonl").write_text(
        '{"iter": 1, "phase": "tdd_green", "reasoning": "first green",'
        ' "verdict_source": "GREEN_CONFIRMED"}\n'
        '{"iter": 2, "phase": "review", "reasoning": "PASS",'
        ' "verdict_source": "PASS"}\n'
        '{"iter": 2, "phase": "approval", "reasoning": "pushed abcd1234",'
        ' "verdict_source": "PUSHED"}\n',
        encoding="utf-8",
    )

    result_path = generate_narrative(tmp_path, goal_id)

    assert result_path == goal_dir / "plan_summary.md"
    assert result_path.exists()
    text = result_path.read_text(encoding="utf-8")
    headers = re.findall(r"^##\s+(\w+)\s*$", text, flags=re.MULTILINE)
    assert headers == ["Purpose", "Plan", "Process", "Result", "Review"], (
        f"expected 5 headers in order, got {headers!r}"
    )
