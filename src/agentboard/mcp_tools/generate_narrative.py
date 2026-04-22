"""MCP dispatch wrapper for agentboard_generate_narrative.

Thin layer over `agentboard.narrative.generator.generate_narrative`: validates
MCP arguments (per `mcp-required-field-check-must-reject-none` learning),
invokes the deterministic assembler, and returns a JSON-serializable dict
with the written `plan_summary_path` plus per-section citation counts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agentboard.narrative.generator import generate_narrative


_CITATION_RE = re.compile(r"\(source:\s*[^)]+\)", re.IGNORECASE)
_H2_RE = re.compile(r"^##\s+([^\n]+?)\s*$", re.MULTILINE)


def _count_citations_per_section(text: str) -> dict[str, int]:
    """Return {section_name: citation_count} by splitting on H2 headers
    and counting `(source: ...)` matches in each body slice."""
    matches = list(_H2_RE.finditer(text))
    out: dict[str, int] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        out[name] = len(_CITATION_RE.findall(body))
    return out


def run_generate_narrative(args: dict[str, Any]) -> dict[str, Any]:
    """MCP handler body. Validates args (None-safe), runs the generator,
    and returns {plan_summary_path, section_citation_counts, missing}."""
    required = ("project_root", "goal_id")
    missing = [f for f in required if args.get(f) is None]
    if missing:
        return {"error": f"missing or null required fields: {missing}"}

    project_root = Path(str(args["project_root"])).resolve()
    goal_id = str(args["goal_id"])

    try:
        out_path = generate_narrative(project_root, goal_id)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # pragma: no cover — defensive
        return {"error": f"generate_narrative failed: {exc!r}"}

    text = out_path.read_text(encoding="utf-8")
    section_counts = _count_citations_per_section(text)
    return {
        "plan_summary_path": str(out_path),
        "section_citation_counts": section_counts,
        "total_citations": sum(section_counts.values()),
    }
