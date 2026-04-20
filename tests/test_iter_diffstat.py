"""Tests for iter-diff numstat parser (s_001-s_002)."""

from devboard.analytics.iter_diffstat import parse_numstat


def test_parse_numstat_regular_row() -> None:
    """Happy path: a single `adds\\tdels\\tpath\\n` numstat row."""
    out = parse_numstat("1\t2\tsrc/a.py\n")
    assert out == [{"path": "src/a.py", "adds": 1, "dels": 2}]


def test_parse_numstat_binary_and_empty() -> None:
    """Edge: binary numstat (-\\t-) and empty input must not crash.

    guards: binary / non-UTF-8 category (numeric parse edge)
    """
    assert parse_numstat("") == []
    out = parse_numstat("-\t-\tassets/logo.png\n1\t0\tREADME.md\n")
    assert out == [
        {"path": "assets/logo.png", "adds": "bin", "dels": "bin"},
        {"path": "README.md", "adds": 1, "dels": 0},
    ]
