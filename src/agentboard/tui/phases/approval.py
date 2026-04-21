"""ApprovalRenderer — APPROVED/REJECTED/PENDING + squash policy.

Canonical: render_markdown == md_from_dict(to_dict(data)).
"""
from __future__ import annotations

from agentboard.tui.phases import PhaseRenderer
from agentboard.tui.phases.types import ApprovalData


def md_from_dict(d: dict) -> str:
    phase = d.get("phase", "approval")
    if phase != "approval":
        raise ValueError(
            f"phase mismatch: approval md_from_dict requires phase=='approval', got {phase!r}"
        )
    iter_n = d.get("iter_n", 0)
    verdict = d.get("verdict", "?")
    squash = d.get("squash_policy", "?")
    return f"- iter {iter_n} · approval · {verdict} (squash: {squash})"


class ApprovalRenderer(PhaseRenderer):
    phase = "approval"

    def to_dict(self, data: ApprovalData) -> dict:
        return {
            "phase": data.phase,
            "iter_n": data.iter_n,
            "ts": data.ts,
            "duration_ms": data.duration_ms,
            "verdict": data.verdict,
            "squash_policy": data.squash_policy,
        }

    def render_markdown(self, data: ApprovalData) -> str:
        return md_from_dict(self.to_dict(data))

    def render_rich(self, data: ApprovalData) -> str:
        return self.render_markdown(data)
