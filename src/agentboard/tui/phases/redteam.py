"""RedteamRenderer — SURVIVED/BROKEN verdict + findings bullet list.

Canonical contract: render_markdown == md_from_dict(to_dict(data)).
"""
from __future__ import annotations

from agentboard.tui.phases import PhaseRenderer
from agentboard.tui.phases.types import RedteamData

_MAX_FINDINGS_INLINE = 3
_MAX_FINDING_CHARS = 80


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def md_from_dict(d: dict) -> str:
    phase = d.get("phase", "redteam")
    if phase != "redteam":
        raise ValueError(
            f"phase mismatch: redteam md_from_dict requires phase=='redteam', got {phase!r}"
        )
    iter_n = d.get("iter_n", 0)
    verdict = d.get("verdict", "?")
    scenarios = d.get("scenarios_tested", 0)
    findings = d.get("findings", [])
    head = f"- iter {iter_n} · redteam · {verdict} ({scenarios} tested)"
    if not findings:
        return head
    shown = findings[:_MAX_FINDINGS_INLINE]
    lines = [head]
    for f in shown:
        lines.append(f"  • {_truncate(str(f), _MAX_FINDING_CHARS)}")
    if len(findings) > _MAX_FINDINGS_INLINE:
        lines.append(f"  • (+{len(findings) - _MAX_FINDINGS_INLINE} more)")
    return "\n".join(lines)


class RedteamRenderer(PhaseRenderer):
    phase = "redteam"

    def to_dict(self, data: RedteamData) -> dict:
        return {
            "phase": data.phase,
            "iter_n": data.iter_n,
            "ts": data.ts,
            "duration_ms": data.duration_ms,
            "verdict": data.verdict,
            "findings": list(data.findings),
            "scenarios_tested": data.scenarios_tested,
        }

    def render_markdown(self, data: RedteamData) -> str:
        return md_from_dict(self.to_dict(data))

    def render_rich(self, data: RedteamData) -> str:
        return self.render_markdown(data)
