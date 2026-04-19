"""Parallel review orchestration: dedupe + aggregate CSO and redteam outputs."""
from devboard.parallel.aggregate import aggregate_verdict
from devboard.parallel.dedupe import dedupe_findings
from devboard.parallel.models import DedupedReport, Finding, OverallVerdict

__all__ = [
    "DedupedReport",
    "Finding",
    "OverallVerdict",
    "aggregate_verdict",
    "dedupe_findings",
]
