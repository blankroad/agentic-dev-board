from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from devboard.parallel.models import DedupedReport, Finding

_SEVERITY_RANK = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}

Key = Tuple[str, int, str, str]


def _key(f: Finding) -> Optional[Key]:
    if f.file is None or f.line is None:
        return None
    return (f.file, f.line, f.category_namespace, f.category)


def _rank(sev: str) -> int:
    return _SEVERITY_RANK.get(sev, -1)


def _collapse_by_key(findings: List[Finding]) -> Tuple[Dict[Key, Finding], List[Finding]]:
    """Group keyed findings by key keeping the highest-severity one. Unkeyed preserved separately."""
    keyed: Dict[Key, Finding] = {}
    unkeyed: List[Finding] = []
    for f in findings:
        k = _key(f)
        if k is None:
            unkeyed.append(f)
            continue
        prior = keyed.get(k)
        if prior is None or _rank(f.severity) > _rank(prior.severity):
            keyed[k] = f
    return keyed, unkeyed


def dedupe_findings(cso_findings: List[Finding], rt_findings: List[Finding]) -> DedupedReport:
    cso_keyed, cso_unkeyed = _collapse_by_key(list(cso_findings))
    rt_keyed, rt_unkeyed = _collapse_by_key(list(rt_findings))

    overlap_keys = set(cso_keyed) & set(rt_keyed)
    overlap_count = len(overlap_keys)

    merged: List[Finding] = []
    seen_overlap: set = set()
    # iterate CSO first to preserve stable ordering
    for k, f in cso_keyed.items():
        if k in overlap_keys:
            rt_f = rt_keyed[k]
            winner = f if _rank(f.severity) >= _rank(rt_f.severity) else rt_f
            merged.append(winner)
            seen_overlap.add(k)
        else:
            merged.append(f)
    for k, f in rt_keyed.items():
        if k not in overlap_keys:
            merged.append(f)

    merged.extend(cso_unkeyed)
    merged.extend(rt_unkeyed)
    return DedupedReport(findings=merged, overlap_count=overlap_count)
