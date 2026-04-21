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


def test_assemble_process_summarizes_redteam_arc_without_per_iter_citations() -> None:
    """v2.3 (g_20260420_231710_1acaa6): assemble_process emits an arc
    summary (round count, BROKEN/SURVIVED tally, final verdict) instead
    of the legacy per-iter citation dump. Raw `(source: decisions.jsonl
    iter=N phase=X)` citations are no longer emitted in the Process
    section — they belong in the Dev tab per-iter cards."""
    from devboard.narrative.generator import assemble_process

    grouped = {
        8: [{"iter": 8, "phase": "redteam", "reasoning": "Round 1 found TypeError in dispatch.",
             "verdict_source": "BROKEN"}],
        11: [{"iter": 11, "phase": "redteam", "reasoning": "Round 4 only MEDIUM/HIGH; no crash.",
              "verdict_source": "SURVIVED"}],
    }

    out = assemble_process(grouped)

    # New arc summary format
    assert "2 round(s)" in out, f"missing round count: {out!r}"
    assert "1 BROKEN" in out and "1 SURVIVED" in out, (
        f"missing BROKEN/SURVIVED tally: {out!r}"
    )
    assert "final=SURVIVED" in out, f"missing final verdict: {out!r}"
    # Legacy per-iter citation template must be gone.
    assert "(source: decisions.jsonl iter=" not in out, (
        f"per-iter citation template leaked into Process: {out!r}"
    )


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


def _normalize_citation(text: str) -> str:
    """Normalize a citation string for superset comparison: lowercase,
    collapse internal whitespace, strip parens + leading 'source:'
    prefix, strip trailing punctuation."""
    s = text.lower().strip()
    s = re.sub(r"^\(source:\s*", "", s)
    s = s.rstrip(").,;:")
    return re.sub(r"[\s,]+", " ", s)


def _citation_tokens(normalized: str) -> set[str]:
    """Extract essential tokens from a normalized citation: artifact
    name (plan.md/decisions.jsonl), iter=N, phase keyword. Used so
    golden shorthand like 'iter=7 review' token-matches generator
    output 'decisions.jsonl iter=7 phase=review'."""
    tokens: set[str] = set()
    # Artifact hints
    for keyword in ("plan.md", "decisions.jsonl", "changes/"):
        if keyword in normalized:
            tokens.add(keyword)
    # iter=N numbers (collect ALL — golden may say 'iter=8, 9, 10')
    for m in re.findall(r"iter\s*=\s*(\d+)", normalized):
        tokens.add(f"iter={m}")
    # Phase keywords (open vocabulary — generator also covers)
    for phase in (
        "review", "redteam", "cso", "approval", "eng_review", "eng review",
        "parallel_review", "tdd_red", "tdd_green", "tdd_refactor",
        "problem", "architecture", "scope decision", "budget",
    ):
        if phase in normalized:
            tokens.add(phase.replace(" ", "_"))
    return tokens


def _extract_citations(section_text: str) -> list[str]:
    """Pull every `(source: ...)` citation from a section body."""
    return re.findall(r"\(source:\s*[^)]+\)", section_text, flags=re.IGNORECASE)


def test_generate_narrative_citations_are_superset_of_audit_golden() -> None:
    """Real-goal integration test: run the generator on the parent
    audit's target (g_20260418_103214_db0261) and assert that every
    citation present in the hand-authored golden_sample.md appears,
    under normalize_citation, in the generator's output. Generated is
    never thinner than golden.

    # guards: unit-tests-on-primitives-dont-prove-integration
    """
    project_root = Path(__file__).resolve().parent.parent
    audit_golden = (
        project_root
        / ".devboard"
        / "goals"
        / "g_20260419_231208_af78bb"
        / "audit"
        / "golden_sample.md"
    )
    if not audit_golden.exists():
        # Parent audit artifacts may have been trimmed from a checkout;
        # skip is acceptable, the fixture-based test above still runs.
        import pytest
        pytest.skip("parent audit golden_sample.md not present in this checkout")

    target_goal_id = "g_20260418_103214_db0261"
    target_plan = project_root / ".devboard" / "goals" / target_goal_id / "plan.md"
    if not target_plan.exists():
        import pytest
        pytest.skip(f"target goal {target_goal_id} plan.md not in this checkout")

    from devboard.narrative.generator import generate_narrative

    out_path = generate_narrative(project_root, target_goal_id)
    generated = out_path.read_text(encoding="utf-8")
    generated_token_sets = [
        _citation_tokens(_normalize_citation(c))
        for c in _extract_citations(generated)
    ]

    golden = audit_golden.read_text(encoding="utf-8")
    golden_citations = _extract_citations(golden)

    # Token-subset acceptance: every golden citation's token set must
    # be a subset of SOME generated citation's token set. This tolerates
    # shorthand drift ('iter=7 review' vs 'decisions.jsonl iter=7 phase=review')
    # while still catching missed artifacts or iter numbers.
    missing: list[str] = []
    for cite in golden_citations:
        g_tokens = _citation_tokens(_normalize_citation(cite))
        if not g_tokens:
            continue  # citation has no extractable tokens, skip
        if not any(g_tokens.issubset(s) for s in generated_token_sets):
            missing.append(cite)

    assert not missing, (
        f"generated narrative missing {len(missing)} citations from audit "
        f"golden_sample.md; first examples: {missing[:10]!r}. "
        f"Generated token sets sample: {generated_token_sets[:5]!r}"
    )
