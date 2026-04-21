"""Parallel review orchestration: dedupe + aggregate CSO and redteam outputs."""
from agentboard.parallel.aggregate import aggregate_verdict
from agentboard.parallel.dedupe import dedupe_findings
from agentboard.parallel.models import DedupedReport, Finding, OverallVerdict

__all__ = [
    "DedupedReport",
    "Finding",
    "OverallVerdict",
    "aggregate_verdict",
    "dedupe_findings",
]
