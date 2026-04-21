"""Overview tab metric card strip — structural + Pilot tests."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ─── s_001 — build_metrics returns 4 cards ─────────────────────────────────

def test_build_metrics_empty_input_returns_4_cards() -> None:
    """s_001 — 4 cards: files_changed / iterations / convergence / tests."""
    from devboard.analytics.overview_metrics import build_metrics

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
    from devboard.analytics.overview_metrics import build_metrics

    cards = build_metrics(decisions=[], plan={}, diff_text="")
    for c in cards:
        assert c.value not in (None, ""), f"card {c.label!r} has empty value"


# ─── s_003 — approval → converged ──────────────────────────────────────────

def test_build_metrics_convergence_from_approval_decision() -> None:
    """s_003 — a `phase=approval verdict_source=PUSHED` entry marks the
    goal as converged."""
    from devboard.analytics.overview_metrics import build_metrics

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
    from devboard.analytics.overview_metrics import build_metrics
    from devboard.tui.overview_cards import render_cards

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
    from devboard.tui.app import DevBoardApp

    app = DevBoardApp(store_root=REPO)
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
    source = (REPO / "src/devboard/tui/phase_flow.py").read_text(encoding="utf-8")
    assert "overview-cards" in source, (
        "phase_flow refresh path must name #overview-cards"
    )


# ─── s_007 — scope guard ───────────────────────────────────────────────────

def test_out_of_scope_unchanged() -> None:
    """s_007 — guard paths untouched vs main."""
    import subprocess

    guarded = [
        "src/devboard/mcp_server.py",
        "src/devboard/cli.py",
        "src/devboard/storage",
        "src/devboard/models.py",
        "src/devboard/gauntlet",
        "src/devboard/tui/verdict_palette.py",
        "src/devboard/analytics/verdict_timeline.py",
        "src/devboard/analytics/diff_parser.py",
        "src/devboard/tui/plan_pipeline.py",
        "src/devboard/tui/review_cards.py",
        "src/devboard/tui/review_timeline.py",
        "src/devboard/tui/process_swimlane.py",
        "src/devboard/tui/process_sparkline.py",
        "src/devboard/tui/dev_file_tree.py",
        "src/devboard/tui/dev_diff_viewer.py",
        "src/devboard/tui/dev_issues_pane.py",
        "src/devboard/tui/overview_render.py",
        "src/devboard/tui/dev_timeline_render.py",
        "src/devboard/tui/review_sections_render.py",
        "src/devboard/tui/result_timeline_render.py",
        "src/devboard/tui/plan_markdown.py",
        "pyproject.toml",
        ".mcp.json",
    ]
    offenders: list[str] = []
    for base in ("main", "origin/main"):
        proc = subprocess.run(
            ["git", "-C", str(REPO), "diff", base, "--", *guarded],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            if proc.stdout:
                for line in proc.stdout.splitlines():
                    if line.startswith("diff --git a/"):
                        offenders.append(line.split()[2].removeprefix("a/"))
            break
    else:
        pytest.skip("no main/origin/main baseline available")
    assert not offenders, (
        f"out-of-scope files changed (scope_guard violation): {offenders}"
    )
