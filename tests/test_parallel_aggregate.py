"""Tests for src/agentboard/parallel/aggregate.py — verdict aggregation rules."""
from __future__ import annotations


def test_aggregate_both_clean_returns_clean() -> None:
    """SECURE + SURVIVED → overall=CLEAN."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v = aggregate_verdict(cso="SECURE", redteam="SURVIVED")
    assert v.status == "CLEAN"
    assert v.reasons == []


def test_aggregate_cso_blocker_propagates() -> None:
    """VULNERABLE + SURVIVED → BLOCKER with reasons=['cso']."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v = aggregate_verdict(cso="VULNERABLE", redteam="SURVIVED")
    assert v.status == "BLOCKER"
    assert v.reasons == ["cso"]


def test_aggregate_redteam_blocker_propagates() -> None:
    """SECURE + BROKEN → BLOCKER with reasons=['redteam']."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v = aggregate_verdict(cso="SECURE", redteam="BROKEN")
    assert v.status == "BLOCKER"
    assert v.reasons == ["redteam"]


def test_aggregate_both_blockers_returns_both() -> None:
    """VULNERABLE + BROKEN → BOTH_BLOCKER with both reasons."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v = aggregate_verdict(cso="VULNERABLE", redteam="BROKEN")
    assert v.status == "BOTH_BLOCKER"
    assert set(v.reasons) == {"cso", "redteam"}


def test_aggregate_incomplete_propagates() -> None:
    """One side INCOMPLETE (crash / no verdict) → overall INCOMPLETE."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v = aggregate_verdict(cso="INCOMPLETE", redteam="SURVIVED")
    assert v.status == "INCOMPLETE"


def test_aggregate_normalizes_case() -> None:
    """Mixed-case sub-agent output must be normalized to the canonical verdict set."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v_mixed = aggregate_verdict(cso="Secure", redteam="Survived")
    v_upper = aggregate_verdict(cso="SECURE", redteam="SURVIVED")
    assert v_mixed.status == v_upper.status == "CLEAN"


def test_aggregate_strips_whitespace() -> None:
    """Leading/trailing whitespace must not drop a valid verdict to INCOMPLETE."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v = aggregate_verdict(cso="  VULNERABLE  ", redteam="SURVIVED")
    assert v.status == "BLOCKER"
    assert v.reasons == ["cso"]


def test_aggregate_both_skipped_returns_clean_with_note() -> None:
    """Both auto-skipped (not production / not security-sensitive) → CLEAN with note."""
    from agentboard.parallel.aggregate import aggregate_verdict

    v = aggregate_verdict(cso="SKIPPED", redteam="SKIPPED")
    assert v.status == "CLEAN"
    assert v.note == "no review needed"
