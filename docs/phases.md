# Phase Renderer Contract

`PhaseRenderer` is the extension point for adding a new phase to Agent Dev
Board v3's canonical pile. Agent frameworks (gstack, OpenHands, Codex,
custom) that emit phase-tagged decisions can register a renderer so their
output appears in the Cinema UI + agent MCP markdown with the same
fidelity as built-in phases (tdd / redteam / approval).

## Contract (src/agentboard/tui/phases/__init__.py)

```python
from abc import ABC, abstractmethod

class PhaseRenderer(ABC):
    phase: str = ""

    @abstractmethod
    def to_dict(self, data) -> dict:
        """Canonical JSON projection for this phase's data."""
```

Any concrete subclass **MUST** implement `to_dict`. Subclasses that
additionally want Cinema UI rendering should implement `render_markdown`
and `render_rich`. The canonical invariant:

```
render_markdown(data) == md_from_dict(to_dict(data))
```

This "json-canonical" design collapses the drift surface from 3 outputs
to 1 — `to_dict` is the single source of truth, markdown and rich are
derived. Contract test in `tests/test_phase_renderer_contract.py`
asserts this property for every registered renderer.

## Worked example: TddRenderer

Source: `src/agentboard/tui/phases/tdd.py`

```python
from agentboard.tui.phases import PhaseRenderer
from agentboard.tui.phases.types import TddIterData


def md_from_dict(d: dict) -> str:
    """Format a tdd iter dict as a single markdown line.

    Validates phase — raises ValueError on cross-phase input
    (redteam F2 fix, schema validation at dispatch boundary).
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
```

## Registering a new phase

1. Create `src/agentboard/tui/phases/<your_phase>.py`
2. Define a typed PhaseData dataclass in `types.py` with `__post_init__`
   Literal validation for enum-ish fields
3. Implement `md_from_dict` with phase guard (raises on mismatch)
4. Implement `to_dict` mapping dataclass → dict, `render_markdown` as
   `md_from_dict(self.to_dict(data))` for canonical invariant
5. Register in `REGISTRY` dict in `__init__.py` (or subclass + late-bind)
6. Add a contract test in `test_phase_renderer_contract.py` asserting
   canonical property + token budget + non-empty output

## Unknown phases

`REGISTRY.get(phase, FallbackRenderer)` gives a sane default for
unrecognized phases. FallbackRenderer emits `{"_fallback": True}` in
its to_dict output so downstream consumers can detect the fallback
path and prompt for a proper renderer.

## Token budgets

Per-phase markdown size limits enforced by contract tests:

| Phase | Budget |
|--|--|
| tdd | ≤150 tok |
| redteam | ≤300 tok |
| approval | ≤100 tok |

These budgets govern the aggregate budget of `chapters/*.md` (≤3k tok)
and `session.md` (≤500 tok) — if your renderer blows its per-iter
budget, the chapter writer's truncation kicks in and details are lost.
