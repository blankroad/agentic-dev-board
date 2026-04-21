"""Contract tests for agentboard.tui.phases.

Verifies PhaseRenderer ABC, typed PhaseData dataclasses, concrete
renderers (tdd/redteam/approval), REGISTRY + FallbackRenderer, and
the json-canonical tri-render property.
"""
from __future__ import annotations

import pytest


def test_phase_renderer_abc_enforces_to_dict() -> None:
    """PhaseRenderer ABC must reject subclasses missing to_dict at
    class-definition / instantiation time, not at first call.

    Guards: explicit-abstract-contract (edge: integration wiring)
    """
    from agentboard.tui.phases import PhaseRenderer  # noqa: F401

    class BrokenRenderer(PhaseRenderer):
        phase = "broken"
        # NOTE: to_dict deliberately omitted — ABC should reject.

    with pytest.raises(TypeError, match="abstract"):
        BrokenRenderer()  # instantiation fails due to abstract method


def test_tdd_iter_data_rejects_invalid_test_result() -> None:
    """TddIterData must reject test_result outside Literal[red|green|refactor]
    at construction time, not later.

    Guards: empty/None input (edge)
    """
    from agentboard.tui.phases.types import TddIterData

    with pytest.raises(ValueError, match="test_result"):
        TddIterData(
            phase="tdd_red",
            iter_n=1,
            ts="2026-01-01T00:00:00Z",
            duration_ms=100,
            test_result="bogus",  # not in Literal
            diff_ref="runs/x/changes/iter-1.diff",
            passed=0,
            failed=1,
        )


def test_tdd_renderer_canonical_projection() -> None:
    """Canonical contract: render_markdown must equal md_from_dict(to_dict(data)).

    This forces implementations to derive markdown from the dict projection,
    collapsing drift surface from 3 to 1.
    """
    from agentboard.tui.phases.tdd import TddRenderer, md_from_dict
    from agentboard.tui.phases.types import TddIterData

    r = TddRenderer()
    data = TddIterData(
        phase="tdd_red",
        iter_n=3,
        ts="2026-01-01T00:00:00Z",
        duration_ms=420,
        test_result="red",
        diff_ref="runs/x/changes/iter-3.diff",
        passed=0,
        failed=1,
    )

    assert md_from_dict(r.to_dict(data)) == r.render_markdown(data)


def test_tdd_renderer_token_budget_150() -> None:
    """TddRenderer markdown must stay within 150-token budget for typical iters."""
    from agentboard.tui.phases.tdd import TddRenderer
    from agentboard.tui.phases.types import TddIterData

    r = TddRenderer()
    data = TddIterData(
        phase="tdd_green",
        iter_n=42,
        ts="2026-01-01T00:00:00Z",
        duration_ms=1234,
        test_result="green",
        diff_ref="runs/x/changes/iter-42.diff",
        passed=127,
        failed=0,
    )

    md = r.render_markdown(data)
    # char-to-token estimate: len / 3.5
    assert len(md) / 3.5 <= 150, f"tdd markdown too long: {len(md)} chars"


def test_redteam_renderer_canonical_and_budget() -> None:
    """RedteamRenderer: canonical projection + markdown ≤300 tok."""
    from agentboard.tui.phases.redteam import RedteamRenderer, md_from_dict
    from agentboard.tui.phases.types import RedteamData

    r = RedteamRenderer()
    data = RedteamData(
        phase="redteam",
        iter_n=8,
        ts="2026-01-01T00:00:00Z",
        duration_ms=2100,
        verdict="BROKEN",
        findings=[
            "scrubber click does not pin Labor scroll",
            "chapter.md race on simultaneous synth",
            "session.md teaser overflows on long title",
        ],
        scenarios_tested=3,
    )

    md = r.render_markdown(data)
    assert md_from_dict(r.to_dict(data)) == md
    assert len(md) / 3.5 <= 300, f"redteam markdown too long: {len(md)} chars"


def test_approval_renderer_canonical_and_budget() -> None:
    """ApprovalRenderer: canonical projection + markdown ≤100 tok."""
    from agentboard.tui.phases.approval import ApprovalRenderer, md_from_dict
    from agentboard.tui.phases.types import ApprovalData

    r = ApprovalRenderer()
    data = ApprovalData(
        phase="approval",
        iter_n=22,
        ts="2026-01-01T00:00:00Z",
        duration_ms=800,
        verdict="APPROVED",
        squash_policy="squash",
    )

    md = r.render_markdown(data)
    assert md_from_dict(r.to_dict(data)) == md
    assert len(md) / 3.5 <= 100, f"approval markdown too long: {len(md)} chars"


def test_registry_lookup_and_fallback() -> None:
    """REGISTRY maps known phases to renderer classes; FallbackRenderer
    handles unknown phases with a _fallback marker in to_dict output.
    """
    from agentboard.tui.phases import REGISTRY, FallbackRenderer
    from agentboard.tui.phases.tdd import TddRenderer

    assert REGISTRY["tdd"] is TddRenderer

    unknown_class = REGISTRY.get("custom_foo", FallbackRenderer)
    assert unknown_class is FallbackRenderer

    r = FallbackRenderer()
    d = r.to_dict({"phase": "custom_foo", "iter_n": 7, "anything": "x"})
    assert d["_fallback"] is True
    assert d["phase"] == "custom_foo"
    md = r.render_markdown({"phase": "custom_foo", "iter_n": 7, "anything": "x"})
    assert "custom_foo" in md
    assert "no renderer" in md.lower()


def test_md_from_dict_rejects_cross_phase_shape() -> None:
    """F2 fix (redteam): md_from_dict must reject input whose phase does
    not match the phase owned by the module. Silent miscategorization
    (tdd.md_from_dict rendering a redteam dict) produces nonsense output.

    guards: type (schema validation on dispatch boundary)
    """
    from agentboard.tui.phases.approval import md_from_dict as approval_md
    from agentboard.tui.phases.redteam import md_from_dict as redteam_md
    from agentboard.tui.phases.tdd import md_from_dict as tdd_md

    # tdd expects phase starting with "tdd"
    with pytest.raises(ValueError, match="phase mismatch"):
        tdd_md({"phase": "redteam", "iter_n": 5})

    # redteam expects phase == "redteam"
    with pytest.raises(ValueError, match="phase mismatch"):
        redteam_md({"phase": "tdd_green", "iter_n": 5})

    # approval expects phase == "approval"
    with pytest.raises(ValueError, match="phase mismatch"):
        approval_md({"phase": "redteam", "iter_n": 5})
