"""Phase B renderer tests — Dev code-review cards + Result shipped count +
Review source-from-payload + scope guard."""

from __future__ import annotations

from pathlib import Path


def _sample_iteration(
    iter_n: int = 1,
    step_id: str = "s_001",
    behavior: str = "overview tab wraps VerticalScroll",
    reasoning: str = "overview TabPane wrapped via import + DEFAULT_CSS",
    test_file: str = "tests/test_tui_center_scroll.py",
    test_name: str = "test_overview_tab_wraps_static_in_vertical_scroll",
    impl_file: str = "src/devboard/tui/phase_flow.py",
) -> dict:
    return {
        "iter": iter_n,
        "phase": "tdd_green",
        "verdict": "GREEN_CONFIRMED",
        "reasoning": reasoning,
        "ts": f"2026-04-20T10:0{iter_n}:00+00:00",
        "touched_files": [],
        "diff_stats": {"adds": 0, "dels": 0},
        "step_id": step_id,
        "behavior": behavior,
        "test_file": test_file,
        "test_name": test_name,
        "impl_file": impl_file,
    }


def test_render_escapes_newlines_in_reasoning() -> None:
    """redteam FM#5 — reasoning with embedded '\\n' must NOT visually
    bleed into subsequent card fields. The renderer must flatten
    newlines (or indent them consistently) so the label contract holds."""
    from devboard.tui.dev_timeline_render import render_dev_timeline

    iteration = _sample_iteration(
        reasoning="first line\nSECOND_LINE_SENTINEL\nthird",
    )
    payload = {"iterations": [iteration], "code_delta": {}}
    out = render_dev_timeline(payload)
    # Split by lines and find the reasoning row — next non-empty line must
    # still be `  test:` (not SECOND_LINE_SENTINEL bleeding in).
    lines = out.splitlines()
    reasoning_idx = next(i for i, l in enumerate(lines) if l.startswith("  reasoning:"))
    # The next label line must appear cleanly. Check that no stray
    # unindented line precedes '  test:'.
    following = lines[reasoning_idx + 1 : reasoning_idx + 5]
    assert any(l.startswith("  test:") for l in following), (
        f"expected '  test:' within 4 lines after reasoning; got:\n"
        + "\n".join(following)
    )
    for l in following:
        if l.startswith("  test:"):
            break
        assert l.startswith("  ") or not l.strip(), (
            f"reasoning continuation must stay indented or empty; "
            f"leaked line: {l!r} in:\n{out}"
        )


def test_render_cards_with_divider_and_rollup_coexist() -> None:
    """s_008 — two cards separated by a divider (5+ '─' chars), AND when
    code_delta is present the rollup ## Scope baseline section co-exists
    with ## Iterations card section."""
    from devboard.tui.dev_timeline_render import render_dev_timeline

    payload = {
        "iterations": [
            _sample_iteration(1, step_id="s_001"),
            _sample_iteration(2, step_id="s_002", behavior="all five tabs wrap"),
        ],
        "code_delta": {
            "base_commit": "da7c4cf",
            "head_commit": "a4149f3",
            "files": [{"path": "src/devboard/tui/phase_flow.py", "adds": 5, "dels": 2}],
            "adds": 5,
            "dels": 2,
        },
    }
    out = render_dev_timeline(payload)
    assert "## Scope baseline" in out, "rollup must still render with code_delta"
    assert "## Iterations" in out, "cards section must render alongside rollup"
    assert "─────" in out, f"divider (5+ ─) missing from output:\n{out}"


def test_out_of_scope_files_untouched() -> None:
    """s_015 — LockedPlan out_of_scope_guard enforcement. These files must
    not have been modified by this goal's changes (git diff vs main
    empty)."""
    import subprocess
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parent.parent
    guarded = [
        "src/devboard/models.py",
        "src/devboard/storage/file_store.py",
        "src/devboard/tui/app.py",
        "src/devboard/tui/phase_flow.py",
        "src/devboard/tui/status_bar.py",
        "src/devboard/tui/plan_markdown.py",
        "src/devboard/tui/goal_side_list.py",
        "src/devboard/tui/activity_row.py",
        "src/devboard/tui/command_line.py",
        "src/devboard/tui/live_status_line.py",
        "src/devboard/mcp_server.py",
        "src/devboard/cli.py",
    ]
    offenders: list[str] = []
    for base in ("main", "origin/main"):
        proc = subprocess.run(
            ["git", "-C", str(repo), "diff", base, "--", *guarded],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            if proc.stdout:
                # collect file names that appear in diff --git headers
                for line in proc.stdout.splitlines():
                    if line.startswith("diff --git a/"):
                        offenders.append(line.split()[2].removeprefix("a/"))
            break
    else:
        import pytest as _pytest

        _pytest.skip("no main/origin/main baseline available")
    assert not offenders, (
        f"guarded files modified (scope_guard violation): {offenders}"
    )


def test_result_shipped_count_uses_step_shipping() -> None:
    """s_010 — result_timeline_render must source 'Shipped N/M' from
    payload.step_shipping, not a hardcoded or plan.json.completed value.
    With step_shipping showing 3 of 3 shipped, output must say 3/3."""
    from devboard.tui.result_timeline_render import render_result_timeline

    payload = {
        "step_shipping": [
            {"id": "s_001", "behavior": "a", "impl_file": "src/devboard/tui/phase_flow.py",
             "shipped": True, "ship_iter": 1, "ship_ts": "t1", "ship_verdict": "GREEN_CONFIRMED"},
            {"id": "s_002", "behavior": "b", "impl_file": "src/devboard/tui/phase_flow.py",
             "shipped": True, "ship_iter": 2, "ship_ts": "t2", "ship_verdict": "GREEN_CONFIRMED"},
            {"id": "s_003", "behavior": "c", "impl_file": "src/devboard/tui/app.py",
             "shipped": True, "ship_iter": 3, "ship_ts": "t3", "ship_verdict": "GREEN_CONFIRMED"},
        ],
        "plan_digest": {"atomic_steps_total": 3, "atomic_steps_done": 0},
    }
    out = render_result_timeline(payload)
    assert "Shipped : 3/3" in out, (
        f"Result must show 3/3 shipped from step_shipping (not 0 from plan_digest):\n{out}"
    )


def test_render_emits_card_labels() -> None:
    """s_007 — render_dev_timeline must emit all four card labels
    (behavior:, reasoning:, test:, impl:) when iterations carry the new
    fields populated by overview_payload."""
    from devboard.tui.dev_timeline_render import render_dev_timeline

    payload = {
        "iterations": [_sample_iteration()],
        "code_delta": {},  # no rollup
    }
    out = render_dev_timeline(payload)
    for label in ("behavior:", "reasoning:", "test:", "impl:"):
        assert label in out, f"label {label!r} missing from output:\n{out}"
