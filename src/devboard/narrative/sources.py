"""Pure readers that parse .devboard/goals/<gid>/ artifacts into
citation-bearing dataclasses. No side effects; every function tolerates
missing files by returning a dataclass with empty fields + an explicit
`missing_*` list."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CANONICAL_PLAN_SECTIONS: tuple[str, ...] = (
    "Problem",
    "Architecture",
    "Scope Decision",
    "Budget",
)


@dataclass
class PlanSections:
    """Parsed H2 sections of a goal's plan.md. Each field holds the raw
    body text (no header line). `missing_sections` lists canonical
    sections that were not found — the caller decides whether to treat
    that as a soft warning or a hard error."""

    problem: str = ""
    architecture: str = ""
    scope_decision: str = ""
    budget: str = ""
    missing_sections: list[str] = field(default_factory=list)


_H2_RE = re.compile(r"^##\s+([^\n]+?)\s*$", re.MULTILINE)


def _split_sections(text: str) -> dict[str, str]:
    """Split a markdown document by H2 headers; return {header_text:
    body_text} where body is everything between this header and the
    next H2 (or EOF)."""
    out: dict[str, str] = {}
    matches = list(_H2_RE.finditer(text))
    for i, m in enumerate(matches):
        header = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[header] = text[body_start:body_end].strip("\n")
    return out


def parse_plan_sections(plan_path: Path) -> PlanSections:
    """Parse `plan.md` H2 sections into a PlanSections dataclass.
    Missing canonical sections populate `missing_sections`; unknown
    extra H2s are silently ignored (we only need the canonical five)."""
    try:
        text = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return PlanSections(missing_sections=list(CANONICAL_PLAN_SECTIONS))

    sections = _split_sections(text)
    missing = [
        name for name in CANONICAL_PLAN_SECTIONS if name not in sections
    ]

    return PlanSections(
        problem=sections.get("Problem", ""),
        architecture=sections.get("Architecture", ""),
        scope_decision=sections.get("Scope Decision", ""),
        budget=sections.get("Budget", ""),
        missing_sections=missing,
    )


def group_decisions_by_iter(
    decisions_path: Path,
) -> dict[int, list[dict[str, Any]]]:
    """Parse decisions.jsonl and group rows by their `iter` field.
    Rows missing `verdict_source` have it coerced to '?'; malformed
    JSON lines and non-dict rows are silently skipped. Returns an
    iter->rows dict (rows preserve file order within each iter)."""
    out: dict[int, list[dict[str, Any]]] = {}
    try:
        text = decisions_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        row.setdefault("verdict_source", "?")
        if row["verdict_source"] is None:
            row["verdict_source"] = "?"
        iter_n = row.get("iter")
        if not isinstance(iter_n, int):
            continue
        out.setdefault(iter_n, []).append(row)
    return out
