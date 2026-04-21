"""Tests for src/agentboard/parallel/models.py — Finding / DedupedReport / OverallVerdict."""
from __future__ import annotations


def test_finding_model_accepts_optional_file_line() -> None:
    """Finding has required fields and file/line are Optional (redteam edge outputs may omit them)."""
    from agentboard.parallel.models import Finding

    # file/line present (CSO style)
    f1 = Finding(
        file="src/foo.py",
        line=42,
        category="SQL_INJECTION",
        category_namespace="OWASP",
        severity="CRITICAL",
        body="user input reaches cursor.execute",
    )
    assert f1.file == "src/foo.py"
    assert f1.line == 42

    # file/line omitted (redteam edge-case style)
    f2 = Finding(
        file=None,
        line=None,
        category="EdgeInput",
        category_namespace="redteam",
        severity="HIGH",
        body="empty string causes KeyError",
    )
    assert f2.file is None
    assert f2.line is None
    assert f2.severity == "HIGH"
