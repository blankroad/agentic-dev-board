"""s_013 + s_014 — narrative/generator.py Process & Review sections must
emit deterministic summaries (phase counts + last verdict), not raw
per-iter citations like `(source: decisions.jsonl iter=N phase=X)`."""

from __future__ import annotations


def test_process_section_is_summary_not_citation() -> None:
    """Process section output must NOT contain the raw
    `(source: decisions.jsonl iter=` citation template — that format
    produced citation-dump text. It MAY keep the aggregate citation
    line ending in `aggregate).`."""
    from devboard.narrative.generator import assemble_process

    grouped = {
        3: [
            {"iter": 3, "phase": "eng_review", "verdict_source": "OK",
             "reasoning": "arch review passed"},
        ],
        7: [
            {"iter": 7, "phase": "redteam", "verdict_source": "BROKEN",
             "reasoning": "first round broke focus routing"},
        ],
        8: [
            {"iter": 8, "phase": "review", "verdict_source": "PASS",
             "reasoning": "loop complete"},
        ],
        9: [
            {"iter": 9, "phase": "redteam", "verdict_source": "SURVIVED",
             "reasoning": "second round clean"},
        ],
    }
    out = assemble_process(grouped)
    # The raw per-iter citation form must be gone.
    assert "(source: decisions.jsonl iter=" not in out, (
        f"Process must not emit raw per-iter citations; still has template in:\n{out}"
    )
    # Phase totals (or similar summary) must remain.
    assert "phase" in out.lower() and "redteam" in out.lower(), (
        f"Process must include phase summary referencing seen phases:\n{out}"
    )
    # "Final redteam verdict" or similar summary line must appear.
    assert "SURVIVED" in out or "redteam" in out, (
        f"Process must reference final redteam outcome:\n{out}"
    )


def test_review_section_is_summary_not_citation() -> None:
    """Review section must NOT emit the raw `(source: decisions.jsonl
    iter=X phase=Y)` citation per row — aggregate summary lines ending
    in `... aggregate).` are allowed."""
    from devboard.narrative.generator import assemble_review

    grouped = {
        7: [
            {"iter": 7, "phase": "redteam", "verdict_source": "BROKEN",
             "reasoning": "found boot focus bug"},
        ],
        8: [
            {"iter": 8, "phase": "parallel_review", "verdict_source": "BLOCKER",
             "reasoning": "routing issues"},
        ],
        9: [
            {"iter": 9, "phase": "redteam", "verdict_source": "SURVIVED",
             "reasoning": "all clear"},
            {"iter": 9, "phase": "parallel_review", "verdict_source": "CLEAN",
             "reasoning": "post-fix"},
        ],
    }
    out = assemble_review(grouped)
    # The per-iter citation form must be gone.
    assert "(source: decisions.jsonl iter=" not in out, (
        f"Review must not emit raw per-iter citations; found in:\n{out}"
    )
    # Verdict summary must still surface.
    assert "CLEAN" in out or "parallel_review" in out.lower(), (
        f"Review must reference final parallel_review verdict:\n{out}"
    )
    assert "BROKEN" in out or "SURVIVED" in out or "redteam" in out.lower(), (
        f"Review must reference redteam findings:\n{out}"
    )
    # Finding count summary expected.
    assert "round" in out.lower() or "finding" in out.lower(), (
        f"Review should mention rounds or findings count:\n{out}"
    )
