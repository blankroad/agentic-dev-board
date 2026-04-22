"""Overview tab metric card strip — structural + Pilot tests."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ─── s_001 — build_metrics returns 4 cards ─────────────────────────────────

def test_build_metrics_empty_input_returns_4_cards() -> None:
    """s_001 — 4 cards: files_changed / iterations / convergence / tests."""
    from agentboard.analytics.overview_metrics import build_metrics

    cards = build_metrics(decisions=[], plan={}, diff_text="")
    assert len(cards) == 4
    labels = {c.label for c in cards}
    for expected in ("files_changed", "iterations", "convergence", "tests"):
        assert any(expected in lab for lab in labels), (
            f"expected label containing {expected!r} in {labels}"
        )


# ─── s_002 — empty input uses n/a placeholders ─────────────────────────────

def test_build_metrics_empty_yields_na_placeholders() -> None:
    """s_002 — Empty input: every card value is 'n/a' (or a zero fallback)
    so downstream render never shows undefined/None.
    edge: empty / None input"""
    from agentboard.analytics.overview_metrics import build_metrics

    cards = build_metrics(decisions=[], plan={}, diff_text="")
    for c in cards:
        assert c.value not in (None, ""), f"card {c.label!r} has empty value"


# ─── s_003 — approval → converged ──────────────────────────────────────────

def test_build_metrics_convergence_from_approval_decision() -> None:
    """s_003 — a `phase=approval verdict_source=PUSHED` entry marks the
    goal as converged."""
    from agentboard.analytics.overview_metrics import build_metrics

    decisions = [
        {"phase": "approval", "iter": 5, "verdict_source": "PUSHED"},
    ]
    cards = build_metrics(decisions=decisions, plan={}, diff_text="")
    conv = next((c for c in cards if "convergence" in c.label), None)
    assert conv is not None
    assert "converged" in str(conv.value).lower()


# ─── s_004 — render_cards includes all labels ──────────────────────────────

def test_render_cards_includes_all_labels() -> None:
    """s_004 — the rendered string shows every card label."""
    from agentboard.analytics.overview_metrics import build_metrics
    from agentboard.tui.overview_cards import render_cards

    cards = build_metrics(decisions=[], plan={}, diff_text="")
    rendered = render_cards(cards)
    for c in cards:
        assert c.label.split("_")[0] in rendered.lower() or c.label in rendered, (
            f"rendered output missing label cue {c.label!r}"
        )


# ─── s_005 — phase_flow mounts OverviewCards ───────────────────────────────

@pytest.mark.asyncio
async def test_phase_flow_overview_mounts_overview_cards() -> None:
    """s_005 — Overview tab has #overview-cards mounted."""
    from agentboard.tui.app import AgentBoardApp

    app = AgentBoardApp(store_root=REPO)
    async with app.run_test() as pilot:
        await pilot.pause()
        try:
            app.query_one("#overview-cards")
        except Exception as exc:
            raise AssertionError(f"#overview-cards not mounted: {exc}")


# ─── s_006 — handle_tick refresh path touches overview-cards ──────────────

def test_phase_flow_refresh_touches_overview_cards() -> None:
    """s_006 — phase_flow source must refresh overview-cards on tick.
    guards: widgets-need-reactive-hook-not-compose-once"""
    source = (REPO / "src/agentboard/tui/phase_flow.py").read_text(encoding="utf-8")
    assert "overview-cards" in source, (
        "phase_flow refresh path must name #overview-cards"
    )


# ─── s_007 — scope guard ───────────────────────────────────────────────────

# historical scope-guard removed (rename-the-world goal)
