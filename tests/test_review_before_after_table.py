"""Structural assertions for the review-before-after-table goal.

Verifies that `agentboard-design-review` and `agentboard-eng-review` SKILL.md
bodies carry a literal `| Pass | Before | After | Fix |` upsert template
with separator row, promotion logic wording, first-run fallback, and that
their installed copies are byte-exact.

Substring-level audit only — behavioral enforcement is out of scope
(see learning `skill-contracts-are-advisory-not-runtime`).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

DR_SRC = REPO / "skills" / "agentboard-design-review" / "SKILL.md"
DR_INSTALLED = REPO / ".claude" / "skills" / "agentboard-design-review" / "SKILL.md"
ER_SRC = REPO / "skills" / "agentboard-eng-review" / "SKILL.md"
ER_INSTALLED = REPO / ".claude" / "skills" / "agentboard-eng-review" / "SKILL.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _body(p: Path) -> str:
    text = _read(p)
    return text.split("\n---\n", 1)[1] if "\n---\n" in text else text


def test_design_review_has_before_after_table_header() -> None:
    """s_001 — design-review SKILL.md body must contain the literal
    `| Pass | Before | After | Fix |` table header so Claude reproduces
    the exact column structure on upsert."""
    body = _body(DR_SRC)
    header_variants = [
        "| Pass | Before | After | Fix |",
        "| Pass | Before | After  | Fix |",
    ]
    assert any(v in body for v in header_variants), (
        "table header literal missing. design-review Phase 4 must show "
        f"one of: {header_variants}"
    )


def test_design_review_has_separator_row() -> None:
    """s_002 — the table MUST have a markdown separator row
    (`| --- | --- | --- | --- |` or equivalent). Without it the doc
    doesn't render as a table in github / local previewers."""
    body = _body(DR_SRC)
    # accept any 4-column separator row (dashes / colons allowed)
    pattern = re.compile(r"^\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*$", re.M)
    assert pattern.search(body), (
        "4-column markdown table separator row missing in design-review body"
    )


def test_design_review_has_promotion_logic() -> None:
    """s_003 — body must name the re-run promotion logic (previous After
    → new Before) via one of: 'promote' / 'promotion' / '승격' / 'carry over' /
    'carry-over'. Without this wording Claude will just overwrite Before=n/a
    on every run.
    guards: skill-contracts-are-advisory-not-runtime"""
    body = _body(DR_SRC)
    keywords = ["promote", "promotion", "승격", "carry over", "carry-over"]
    assert any(k in body for k in keywords), (
        f"Before-promotion keyword missing; expected one of {keywords}"
    )


def test_design_review_has_first_run_fallback() -> None:
    """s_004 — first run (no prior ## Design Review section) must explicitly
    name the `n/a` fallback so reviewers understand a blank Before doesn't
    mean missing data — it means 'no prior review on this goal'."""
    body = _body(DR_SRC)
    assert "n/a" in body, (
        "first-run `n/a` fallback not mentioned in design-review body"
    )
    # also require some framing prose — not just a bare string in an example
    fallback_phrases = [
        "first run",
        "first-run",
        "first review",
        "no prior",
        "on the first",
    ]
    assert any(p in body.lower() for p in fallback_phrases), (
        f"first-run fallback must be framed in prose (not only in the example table); "
        f"expected one of {fallback_phrases}"
    )


def test_eng_review_has_upsert_section_and_table() -> None:
    """s_005 — eng-review SKILL.md body must introduce a new arch.md upsert
    step whose target heading is `## Engineering Review` and whose body is
    the same 4-column | Check/Pass | Before | After | Fix | table."""
    body = _body(ER_SRC)
    assert "## Engineering Review" in body, (
        "eng-review must upsert into arch.md under the literal "
        "`## Engineering Review` heading"
    )
    header_variants = [
        "| Check | Before | After | Fix |",
        "| Pass | Before | After | Fix |",
    ]
    assert any(v in body for v in header_variants), (
        f"eng-review upsert table header missing; expected one of {header_variants}"
    )
    # separator row must exist too
    pattern = re.compile(r"^\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*$", re.M)
    assert pattern.search(body), (
        "eng-review body must include a 4-column markdown separator row"
    )


def test_eng_review_has_promotion_and_fallback() -> None:
    """s_006 — eng-review body must name both the Before-promotion logic
    and the first-run `n/a` fallback, matching the design-review contract.
    guards: skill-contracts-are-advisory-not-runtime"""
    body = _body(ER_SRC)
    keywords = ["promote", "promotion", "승격", "carry over", "carry-over"]
    assert any(k in body for k in keywords), (
        f"eng-review promotion keyword missing; expected one of {keywords}"
    )
    assert "n/a" in body, "eng-review first-run `n/a` fallback missing"


def test_eng_review_upsert_order_documented() -> None:
    """s_007 — eng-review body must document the execution sequence so
    the new arch.md upsert step runs BEFORE the checkpoint + log_decision,
    and failures fall through as NEEDS_REVISION rather than being silently
    dropped. This catches FM2 (handoff ordering) from challenge.md."""
    body = _body(ER_SRC)
    lower = body.lower()
    # Must mention all three phase words in a context that implies ordering
    for tok in ("upsert", "checkpoint", "log_decision"):
        assert tok in lower, f"eng-review body must name '{tok}' in execution order"
    # Upsert must be documented before checkpoint in the running text
    upsert_pos = lower.find("upsert")
    checkpoint_pos = lower.find("checkpoint")
    assert upsert_pos != -1 and checkpoint_pos != -1 and upsert_pos < checkpoint_pos, (
        "upsert must be documented before checkpoint in the eng-review body"
    )


def test_design_review_installed_synced() -> None:
    """s_008 — .claude/skills/agentboard-design-review/SKILL.md must be
    byte-exact to the source."""
    assert DR_INSTALLED.exists(), f"installed copy missing at {DR_INSTALLED}"
    assert DR_SRC.read_bytes() == DR_INSTALLED.read_bytes(), (
        "design-review installed copy diverges from source — run "
        "`cp skills/agentboard-design-review/SKILL.md "
        ".claude/skills/agentboard-design-review/SKILL.md`"
    )


def test_eng_review_installed_synced() -> None:
    """s_009 — .claude/skills/agentboard-eng-review/SKILL.md must be
    byte-exact to the source."""
    assert ER_INSTALLED.exists(), f"installed copy missing at {ER_INSTALLED}"
    assert ER_SRC.read_bytes() == ER_INSTALLED.read_bytes(), (
        "eng-review installed copy diverges from source — run "
        "`cp skills/agentboard-eng-review/SKILL.md "
        ".claude/skills/agentboard-eng-review/SKILL.md`"
    )


def test_out_of_scope_unchanged() -> None:
    """s_010 — guarded files outside this goal must have no diff vs main."""
    import subprocess

    guarded = [
        "skills/agentboard-brainstorm/SKILL.md",
        "skills/agentboard-gauntlet/SKILL.md",
        "skills/agentboard-tdd/SKILL.md",
        "skills/agentboard-cso/SKILL.md",
        "skills/agentboard-redteam/SKILL.md",
        "skills/agentboard-parallel-review/SKILL.md",
        "skills/agentboard-approval/SKILL.md",
        "skills/agentboard-rca/SKILL.md",
        "skills/agentboard-retro/SKILL.md",
        "skills/agentboard-replay/SKILL.md",
        "skills/agentboard-synthesize-report/SKILL.md",
        "skills/agentboard-ui-preview/SKILL.md",
        "skills/agentboard-dep-audit/SKILL.md",
        "src/devboard",
        "pyproject.toml",
        ".mcp.json",
    ]
    offenders: list[str] = []
    for base in ("main", "origin/main"):
        proc = subprocess.run(
            ["git", "-C", str(REPO), "diff", base, "--", *guarded],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            if proc.stdout:
                for line in proc.stdout.splitlines():
                    if line.startswith("diff --git a/"):
                        offenders.append(line.split()[2].removeprefix("a/"))
            break
    else:
        import pytest as _pytest
        _pytest.skip("no main/origin/main baseline available")
    assert not offenders, (
        f"out-of-scope files changed (scope_guard violation): {offenders}"
    )
