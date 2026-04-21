"""Tests for src/agentboard/parallel/dedupe.py."""
from __future__ import annotations


def _mk(file: str | None = "src/x.py", line: int | None = 1, category: str = "C",
        category_namespace: str = "OWASP", severity: str = "HIGH", body: str = "b"):
    from agentboard.parallel.models import Finding
    return Finding(
        file=file, line=line, category=category, category_namespace=category_namespace,
        severity=severity, body=body,
    )


def test_dedupe_empty_input_returns_empty() -> None:
    """dedupe_findings([], []) returns empty DedupedReport."""
    from agentboard.parallel.dedupe import dedupe_findings

    report = dedupe_findings([], [])
    assert report.findings == []


def test_dedupe_single_finding_unchanged() -> None:
    """When only one side has a finding, it is preserved as-is."""
    from agentboard.parallel.dedupe import dedupe_findings

    only_cso = [_mk(file="src/a.py", line=10, category="SQLi", category_namespace="OWASP")]
    report = dedupe_findings(only_cso, [])
    assert len(report.findings) == 1
    assert report.findings[0].category == "SQLi"


def test_dedupe_different_namespace_keeps_both() -> None:
    """Same (file, line) but different category_namespace = distinct attack vectors — preserve both."""
    from agentboard.parallel.dedupe import dedupe_findings

    cso = [_mk(file="src/a.py", line=10, category="SQLi", category_namespace="OWASP", severity="HIGH")]
    rt = [_mk(file="src/a.py", line=10, category="IntegerOverflow", category_namespace="redteam", severity="HIGH")]
    report = dedupe_findings(cso, rt)
    assert len(report.findings) == 2
    namespaces = {f.category_namespace for f in report.findings}
    assert namespaces == {"OWASP", "redteam"}


def test_dedupe_within_cso_duplicates_not_counted_as_overlap() -> None:
    # guards: overlap-count-must-track-origin-not-keyspace-collisions
    """Within-CSO duplicates must dedup silently — overlap_count measures CSO vs redteam only."""
    from agentboard.parallel.dedupe import dedupe_findings

    f = _mk(file="a.py", line=1, category="C1", category_namespace="OWASP", severity="HIGH")
    report = dedupe_findings([f, f], [])  # within-CSO dup, no redteam finding
    assert report.overlap_count == 0
    assert len(report.findings) == 1


def test_dedupe_reports_overlap_count() -> None:
    """DedupedReport.overlap_count equals number of matched-and-collapsed pairs."""
    from agentboard.parallel.dedupe import dedupe_findings

    cso = [
        _mk(file="a.py", line=1, category="C1", category_namespace="OWASP", severity="HIGH"),
        _mk(file="b.py", line=2, category="C2", category_namespace="OWASP", severity="HIGH"),
    ]
    rt = [
        _mk(file="a.py", line=1, category="C1", category_namespace="OWASP", severity="CRITICAL"),  # overlap
        _mk(file="c.py", line=3, category="C3", category_namespace="redteam", severity="HIGH"),    # unique
    ]
    report = dedupe_findings(cso, rt)
    assert report.overlap_count == 1
    # Sanity: surviving findings = 2 unique + 1 merged = 3
    assert len(report.findings) == 3


def test_dedupe_same_category_keeps_higher_severity() -> None:
    """Same (file, line, namespace, category) on both sides — keep higher severity, single entry."""
    from agentboard.parallel.dedupe import dedupe_findings

    cso = [_mk(file="src/a.py", line=10, category="SQLi", category_namespace="OWASP", severity="HIGH")]
    # e.g. redteam independently hit the same spot but rated it CRITICAL
    rt = [_mk(file="src/a.py", line=10, category="SQLi", category_namespace="OWASP", severity="CRITICAL")]
    report = dedupe_findings(cso, rt)
    assert len(report.findings) == 1
    assert report.findings[0].severity == "CRITICAL"
