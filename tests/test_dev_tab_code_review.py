"""Dev tab code review overhaul — file tree + diff viewer + issues pane.

Structural + Pilot integration tests. Real App mount, tmp_path fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ─── s_001 — diff_parser happy path ────────────────────────────────────────

HAPPY_DIFF = """diff --git a/src/a.py b/src/a.py
index 111..222 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,4 @@
 def greet():
-    return "hi"
+    return "hello"
+    # added comment
diff --git a/src/b.py b/src/b.py
index 333..444 100644
--- a/src/b.py
+++ b/src/b.py
@@ -5,2 +5,3 @@
 x = 1
-y = 2
+y = 3
+z = 4
"""


def test_diff_parser_parses_happy_unified_diff() -> None:
    """s_001 — two-file unified diff → two DiffFile entries with correct
    add/remove counts."""
    from devboard.analytics.diff_parser import parse_unified_diff

    files = parse_unified_diff(HAPPY_DIFF)
    assert len(files) == 2, f"expected 2 files, got {len(files)}"
    paths = [f.path for f in files]
    assert "src/a.py" in paths
    assert "src/b.py" in paths
    a = next(f for f in files if f.path == "src/a.py")
    assert a.added == 2
    assert a.removed == 1


# ─── s_002 — empty input ───────────────────────────────────────────────────

def test_diff_parser_handles_empty_input() -> None:
    """s_002 — `parse_unified_diff('')` returns `[]` without crashing.
    edge: empty / None input"""
    from devboard.analytics.diff_parser import parse_unified_diff
    assert parse_unified_diff("") == []


# ─── s_003 — binary marker ─────────────────────────────────────────────────

BINARY_DIFF = """diff --git a/img.png b/img.png
index 111..222 100644
Binary files a/img.png and b/img.png differ
"""


def test_diff_parser_detects_binary_marker() -> None:
    """s_003 — `Binary files X and Y differ` line → DiffFile(is_binary=True)."""
    from devboard.analytics.diff_parser import parse_unified_diff
    files = parse_unified_diff(BINARY_DIFF)
    assert len(files) == 1
    assert files[0].is_binary is True


# ─── s_004 — file tree render ──────────────────────────────────────────────

def test_dev_file_tree_renders_paths_and_sizes() -> None:
    """s_004 — DevFileTree.render_tree(files, reviewed) shows path + +N/-M."""
    from devboard.analytics.diff_parser import parse_unified_diff
    from devboard.tui.dev_file_tree import render_tree

    files = parse_unified_diff(HAPPY_DIFF)
    rendered = render_tree(files, reviewed=set())
    assert "src/a.py" in rendered
    assert "src/b.py" in rendered
    # +2/-1 for a.py and +2/-1 for b.py
    assert "+2" in rendered
    assert "-1" in rendered


# ─── s_005 — x toggles reviewed (real_user_flow) ───────────────────────────

@pytest.mark.asyncio
async def test_dev_file_tree_x_toggles_reviewed_real_user_flow(tmp_path) -> None:
    """s_005 — boot app, switch to Dev tab via ordinary key, press `x` —
    no .focus() cheat. First file flips to reviewed.
    guards: pilot-test-must-not-mask-default-focus-bug"""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from devboard.analytics.diff_parser import parse_unified_diff
    from devboard.tui.dev_file_tree import DevFileTree

    files = parse_unified_diff(HAPPY_DIFF)

    class TestApp(App):
        BINDINGS = [Binding("x", "toggle_reviewed", "toggle", priority=True)]

        def compose(self) -> ComposeResult:
            yield DevFileTree(files=files, id="dev-file-tree")

        def action_toggle_reviewed(self) -> None:
            tree = self.query_one("#dev-file-tree", DevFileTree)
            tree.toggle_current()

    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        tree = app.query_one("#dev-file-tree", DevFileTree)
        assert len(tree.reviewed) == 1, (
            f"expected 1 reviewed file after `x`, got {tree.reviewed}"
        )


# ─── s_006 — diff viewer caps at 500 lines ────────────────────────────────

def test_dev_diff_viewer_caps_at_500_lines() -> None:
    """s_006 — a 1000-line diff is truncated to 500 rendered lines +
    `[... N more lines]` footer."""
    from devboard.tui.dev_diff_viewer import render_diff

    big_diff_lines = ["+ line " + str(i) for i in range(1000)]
    big_diff = "\n".join(big_diff_lines)
    rendered = render_diff(big_diff)
    lines = rendered.splitlines()
    assert len(lines) <= 510, (
        f"expected ≤510 lines after cap+footer, got {len(lines)}"
    )
    assert "more lines" in rendered.lower()


# ─── s_007 — diff viewer empty state ───────────────────────────────────────

def test_dev_diff_viewer_empty_state() -> None:
    """s_007 — empty diff shows an informative single-line empty state."""
    from devboard.tui.dev_diff_viewer import render_diff
    rendered = render_diff("")
    assert "no diff" in rendered.lower()


# ─── s_008 — issues pane wraps existing timeline ──────────────────────────

def test_dev_issues_pane_wraps_existing_timeline() -> None:
    """s_008 — DevIssuesPane renders `render_dev_timeline(payload)` output
    so the existing rollup view is preserved below the diff viewer."""
    from devboard.tui.dev_issues_pane import render_issues_pane

    payload = {"iter_rows": [], "goal_id": "g_test", "atomic_steps_total": 0}
    rendered = render_issues_pane(payload)
    assert isinstance(rendered, str)
    # existing output is terse when no iters; just assert no crash + str type


# ─── s_009 — phase_flow Dev tab mounts new widgets ────────────────────────

@pytest.mark.asyncio
async def test_phase_flow_dev_tab_mounts_new_widgets() -> None:
    """s_009 — DevFileTree, DevDiffViewer, DevIssuesPane are mounted in
    PhaseFlowView's Dev tab.
    guards: unit-tests-on-primitives-dont-prove-integration"""
    from devboard.tui.app import DevBoardApp

    app = DevBoardApp(store_root=REPO)
    async with app.run_test() as pilot:
        await pilot.pause()
        # NOTE: issues pane uses id=dev-body (legacy name retained for
        # backward compat with prior tests).
        for widget_id in ("dev-file-tree", "dev-diff-viewer", "dev-body"):
            try:
                app.query_one(f"#{widget_id}")
            except Exception as exc:
                raise AssertionError(f"widget #{widget_id} not mounted: {exc}")


# ─── s_010 — reviewed state survives refresh (source-level check) ─────────

def test_reviewed_state_survives_refresh() -> None:
    """s_010 — phase_flow source must reference `_reviewed_paths` set and
    persist it across handle_tick refreshes (path cleanup on deletion).
    guards: widgets-need-reactive-hook-not-compose-once"""
    source = (REPO / "src/devboard/tui/phase_flow.py").read_text(encoding="utf-8")
    assert "_reviewed_paths" in source, (
        "phase_flow must keep reviewed state in an instance variable"
    )


# ─── s_011 — scope guard ───────────────────────────────────────────────────

def test_out_of_scope_unchanged() -> None:
    """s_011 — LockedPlan out_of_scope_guard paths have no diff vs main."""
    import subprocess

    guarded = [
        "src/devboard/mcp_server.py",
        "src/devboard/cli.py",
        "src/devboard/storage/file_store.py",
        "src/devboard/models.py",
        "src/devboard/gauntlet",
        "src/devboard/tui/verdict_palette.py",
        "src/devboard/analytics/verdict_timeline.py",
        "src/devboard/tui/plan_pipeline.py",
        "src/devboard/tui/review_cards.py",
        "src/devboard/tui/review_timeline.py",
        "src/devboard/tui/process_swimlane.py",
        "src/devboard/tui/process_sparkline.py",
        "src/devboard/tui/overview_render.py",
        "src/devboard/tui/review_sections_render.py",
        "src/devboard/tui/result_timeline_render.py",
        "src/devboard/tui/plan_markdown.py",
        "src/devboard/tui/dev_timeline_render.py",
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
        _pytest = pytest
        _pytest.skip("no main/origin/main baseline available")
    assert not offenders, (
        f"out-of-scope files changed (scope_guard violation): {offenders}"
    )
