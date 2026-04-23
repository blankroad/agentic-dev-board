"""Dev tab pile integration tests (M1b m_012-m_016).

Mostly unit-level helper tests + 1 Pilot smoke. m_012-m_015 verify
the helper functions added to phase_flow.py; m_016 is the Pilot
integration that ties them together.
"""
from __future__ import annotations

import json

import pytest


def _seed_pile(tmp_path, rid: str, gid: str, tid: str) -> None:
    from agentboard.storage.file_store import FileStore
    store = FileStore(tmp_path)
    diff_text = """diff --git a/src/foo.py b/src/foo.py
--- a/src/foo.py
+++ b/src/foo.py
@@ -1 +1 @@
-old
+new
"""
    task_changes = tmp_path / ".agentboard" / "goals" / gid / "tasks" / tid / "changes"
    task_changes.mkdir(parents=True)
    (task_changes / "iter_1.diff").write_text(diff_text, encoding="utf-8")
    store.write_iter_artifact(rid, 1, {
        "phase": "tdd_red", "iter_n": 1, "diff_ref": "changes/iter_1.diff",
    }, gid=gid, tid=tid)


def test_dev_tab_uses_pile_when_present_falls_back_to_git(tmp_path) -> None:
    """m_012: dev_tab_load_files() returns pile data when rid provided and
    pile exists; returns empty list when no pile (git fallback signal).
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.tui.phase_flow import dev_tab_load_files

    rid, gid, tid = "run_dt", "g_dt", "t_dt"
    _seed_pile(tmp_path, rid, gid, tid)

    store = FileStore(tmp_path)
    files_pile = dev_tab_load_files(store, rid)
    assert any(f.path == "src/foo.py" for f in files_pile), "pile path missing"

    # No rid → empty (caller falls back to git subprocess)
    files_no_pile = dev_tab_load_files(store, None)
    assert files_no_pile == []


def test_dev_tab_default_view_mode_final_diff() -> None:
    """m_013: dev_tab_default_view_mode() returns 'final_diff'."""
    from agentboard.tui.phase_flow import dev_tab_default_view_mode
    assert dev_tab_default_view_mode() == "final_diff"


def test_dev_tab_view_mode_keybindings() -> None:
    """m_014: dev_tab_view_mode_for_key('1'/'2'/'3') maps to view modes."""
    from agentboard.tui.phase_flow import dev_tab_view_mode_for_key

    assert dev_tab_view_mode_for_key("1") == "final_diff"
    assert dev_tab_view_mode_for_key("2") == "all_iters"
    assert dev_tab_view_mode_for_key("3") == "per_file_timeline"
    assert dev_tab_view_mode_for_key("x") is None  # unknown key → no change


def test_dev_tab_responsive_layout_switches() -> None:
    """m_015: dev_tab_responsive_layout(width) wires through responsive helper."""
    from agentboard.tui.phase_flow import dev_tab_responsive_layout

    assert dev_tab_responsive_layout(120) == "3pane"
    assert dev_tab_responsive_layout(110) == "2pane"
    assert dev_tab_responsive_layout(85) == "1pane"
    assert dev_tab_responsive_layout(70) == "banner"


async def test_dev_tab_e2e_pilot_smoke(tmp_path) -> None:
    """m_016: Pilot smoke — DrawerContainer mounts inside the Dev tab area
    and ScrubberSegmentClicked → drawer opens.

    Scoped: doesn't mount the full AgentBoardApp (heavy + fixture-heavy);
    instead mounts a minimal app that wires PerFileScrubber +
    DrawerContainer the same way phase_flow does, asserting the
    end-to-end click → drawer-open → close → focus-restore sequence.
    """
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.widgets import Static

    from agentboard.tui.inline_drawer import DrawerContainer
    from agentboard.tui.per_file_scrubber import PerFileScrubber, ScrubberSegmentClicked

    class _Smoke(App):
        def __init__(self) -> None:
            super().__init__()
            self.last_click_iter: int | None = None

        def compose(self) -> ComposeResult:
            yield Vertical(
                PerFileScrubber(
                    file_path="src/foo.py",
                    phases=["tdd_red", "tdd_green", "redteam"],
                    id="scrubber",
                ),
                DrawerContainer(id="dc"),
                id="root",
            )

        def on_scrubber_segment_clicked(
            self, event: ScrubberSegmentClicked
        ) -> None:
            self.last_click_iter = event.iter_n
            container = self.query_one("#dc", DrawerContainer)
            scrub = self.query_one("#scrubber", PerFileScrubber)
            self.run_worker(
                container.open(
                    Static(f"iter {event.iter_n} content", id="drawer-content"),
                    trigger=scrub,
                ),
                exclusive=True,
            )

    app = _Smoke()
    async with app.run_test() as pilot:
        scrubber = app.query_one("#scrubber", PerFileScrubber)
        scrubber.focus()
        await pilot.pause()

        # Simulate click on first segment
        await pilot.click("#scrubber", offset=(0, 0))
        await pilot.pause()
        await pilot.pause()  # second pause to allow worker mount

        assert app.last_click_iter == 1, f"click did not dispatch correctly; last_click_iter={app.last_click_iter}"
        # Drawer content present
        contents = app.query("#drawer-content")
        assert len(contents) == 1, "drawer content not mounted on click"

        # Close drawer + verify focus restore
        container = app.query_one("#dc", DrawerContainer)
        await container.close()
        await pilot.pause()
        assert len(app.query("#drawer-content")) == 0
        assert app.focused is scrubber
