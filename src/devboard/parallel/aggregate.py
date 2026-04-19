from __future__ import annotations

from devboard.parallel.models import OverallVerdict

_CSO_CLEAN = {"SECURE", "SKIPPED"}
_RT_CLEAN = {"SURVIVED", "SKIPPED"}
_CSO_BLOCK = {"VULNERABLE"}
_RT_BLOCK = {"BROKEN"}


def aggregate_verdict(cso: str, redteam: str) -> OverallVerdict:
    cso = (cso or "").strip().upper()
    redteam = (redteam or "").strip().upper()
    if cso == "INCOMPLETE" or redteam == "INCOMPLETE":
        return OverallVerdict(status="INCOMPLETE")

    cso_blocked = cso in _CSO_BLOCK
    rt_blocked = redteam in _RT_BLOCK
    if cso_blocked and rt_blocked:
        return OverallVerdict(status="BOTH_BLOCKER", reasons=["cso", "redteam"])
    if cso_blocked:
        return OverallVerdict(status="BLOCKER", reasons=["cso"])
    if rt_blocked:
        return OverallVerdict(status="BLOCKER", reasons=["redteam"])

    if cso in _CSO_CLEAN and redteam in _RT_CLEAN:
        note = "no review needed" if cso == "SKIPPED" and redteam == "SKIPPED" else None
        return OverallVerdict(status="CLEAN", note=note)

    return OverallVerdict(status="INCOMPLETE")
