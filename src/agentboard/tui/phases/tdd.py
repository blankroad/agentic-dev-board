"""TddRenderer — canonical (to_dict), derived markdown, rich stub.

md_from_dict is the shared formatting function. render_markdown is a
thin wrapper that forces the canonical path: derive from to_dict(data).
"""
from __future__ import annotations

from agentboard.tui.phases import PhaseRenderer
from agentboard.tui.phases.types import TddIterData


def md_from_dict(d: dict) -> str:
    """Format a tdd iter dict as a single markdown line.

    Rejects dicts whose phase does not belong to the tdd family —
    silent cross-phase rendering (e.g. feeding a redteam dict in) was
    a redteam finding (F2) because .get() defaults produced plausible
    nonsense output with no error signal.
    """
    phase = d.get("phase", "tdd")
    if not str(phase).startswith("tdd"):
        raise ValueError(
            f"phase mismatch: tdd md_from_dict requires phase startswith 'tdd', got {phase!r}"
        )
    iter_n = d.get("iter_n", 0)
    test_result = d.get("test_result", "?")
    passed = d.get("passed", 0)
    failed = d.get("failed", 0)
    duration_s = d.get("duration_ms", 0) / 1000
    return (
        f"- iter {iter_n} · {phase} · {duration_s:.1f}s · "
        f"{test_result.upper()} ({passed}P/{failed}F)"
    )


class TddRenderer(PhaseRenderer):
    phase = "tdd"

    def to_dict(self, data: TddIterData) -> dict:
        return {
            "phase": data.phase,
            "iter_n": data.iter_n,
            "ts": data.ts,
            "duration_ms": data.duration_ms,
            "test_result": data.test_result,
            "diff_ref": data.diff_ref,
            "passed": data.passed,
            "failed": data.failed,
        }

    def render_markdown(self, data: TddIterData) -> str:
        return md_from_dict(self.to_dict(data))

    def render_rich(self, data: TddIterData) -> str:
        # Stub for M1a-data — M1b consumes with real Rich widgets
        return self.render_markdown(data)
