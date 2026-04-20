"""Parse git-style `--numstat` text into per-file add/del counts.

Used by OverviewPayload builder to surface code-level activity per iter
in the TUI Dev timeline without AST / LLM analysis.
"""

from __future__ import annotations


def parse_numstat(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        adds_s, dels_s, path = parts
        if adds_s == "-" and dels_s == "-":
            rows.append({"path": path, "adds": "bin", "dels": "bin"})
            continue
        try:
            adds, dels = int(adds_s), int(dels_s)
        except ValueError:
            continue
        rows.append({"path": path, "adds": adds, "dels": dels})
    return rows
