from __future__ import annotations

from pathlib import Path


_MIGRATED_V20_TESTS = {
    # These v2.0-specific tests were removed during the v2.1 migration.
    # They asserted ContextViewer tabs / ResourcesView Runs / LiveStreamView
    # as a 45% pane — all of which v2.1 replaces with StatusBar, PlanMarkdown,
    # ActivityTimeline, MetaPane, FilesChangedPane. v2.1 equivalents live in
    # tests/test_tui_v21_smoke.py and the per-widget test files.
    "test_app_launches_with_empty_devboard_shows_empty_state",
    "test_colon_runs_populates_runs_list",
    "test_colon_diff_loads_diff_tab",
    "test_colon_decisions_loads_decisions_tab",
    "test_colon_learn_renders_results",
    "test_number_keys_switch_context_tabs",
    "test_context_viewer_auto_loads_latest_task_diff_on_launch",
    "test_live_stream_docked_bottom_with_small_default_height",
    "test_backslash_toggles_live_stream_expansion",
    "test_plan_tab_renders_markdown_with_rich_formatting",
    "test_context_viewer_diff_tab_default_is_action_prompt",
    "test_context_viewer_plan_tab_loads_active_goal_plan",
    "test_live_stream_renders_human_line_not_raw_json",
    "test_live_stream_colors_redteam_broken_red",
    "test_app_wires_tail_worker_to_live_stream",
    "test_live_stream_applies_rich_color_markup_for_anomalies",
}


def test_legacy_specific_tests_are_enumerated() -> None:
    """v2.1 migration gate. For every v2.0-specific test listed above,
    assert that it has been removed from the active suite — i.e. its
    name is not present as a test function in any tests/test_tui*.py.
    This prevents silent partial migrations."""
    tests_dir = Path(__file__).resolve().parent
    active_names: set[str] = set()
    for py_file in tests_dir.glob("test_tui_*.py"):
        text = py_file.read_text()
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("async def test_") or s.startswith("def test_"):
                prefix = "async def " if s.startswith("async def ") else "def "
                name = s[len(prefix):].split("(", 1)[0].strip()
                active_names.add(name)
    still_present = _MIGRATED_V20_TESTS & active_names
    assert not still_present, (
        f"v2.0-specific tests leaked back into active suite: {still_present}"
    )
