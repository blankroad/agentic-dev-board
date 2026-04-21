"""Phase-typed renderer contract for Agent Dev Board v3.

Provides PhaseRenderer ABC whose concrete implementations emit three
projections of one `PhaseData` input: `to_dict` (canonical JSON),
`render_markdown` (derived from to_dict), and `render_rich` (Textual/Rich
renderable, stubbed in M1a-data).

REGISTRY maps known phase names to their renderer class. For unknown
phase names, callers should use REGISTRY.get(phase, FallbackRenderer)
to get a sensible default that emits a _fallback marker.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PhaseRenderer(ABC):
    """Abstract base for all phase-typed renderers.

    Each concrete subclass MUST implement `to_dict` — the canonical
    projection from which markdown / rich outputs are derived.
    """

    phase: str = ""

    @abstractmethod
    def to_dict(self, data: Any) -> dict:
        """Canonical JSON projection for this phase's data."""


class FallbackRenderer(PhaseRenderer):
    """Default renderer for unknown phases.

    Accepts any input shape. to_dict wraps it with a `_fallback: True`
    marker so consumers know this was NOT rendered by a phase-specific
    renderer. render_markdown emits a single visible line naming the
    phase so the pile remains informative.
    """

    phase = "_fallback"

    def to_dict(self, data: Any) -> dict:
        if isinstance(data, dict):
            out = dict(data)
        else:
            out = {"_raw": str(data)}
        out["_fallback"] = True
        out.setdefault("phase", "unknown")
        return out

    def render_markdown(self, data: Any) -> str:
        d = self.to_dict(data)
        return f"- iter {d.get('iter_n', '?')} · {d.get('phase')} (no renderer)"

    def render_rich(self, data: Any) -> str:
        return self.render_markdown(data)


def _build_registry() -> dict[str, type[PhaseRenderer]]:
    """Import-time registry build. Isolated to a function so tests can
    monkeypatch/rebuild if needed.
    """
    from agentboard.tui.phases.tdd import TddRenderer
    from agentboard.tui.phases.redteam import RedteamRenderer
    from agentboard.tui.phases.approval import ApprovalRenderer

    return {
        "tdd": TddRenderer,
        "tdd_red": TddRenderer,
        "tdd_green": TddRenderer,
        "tdd_refactor": TddRenderer,
        "redteam": RedteamRenderer,
        "approval": ApprovalRenderer,
    }


REGISTRY: dict[str, type[PhaseRenderer]] = _build_registry()
