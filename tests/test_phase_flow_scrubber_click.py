"""Cinema interactive click→drawer wiring tests (M1c-interactive c_001-c_005)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll


def _seed_pile_with_scrubber(tmp_path: Path, rid: str, tid: str, gid: str) -> None:
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_digest import DigestWriter

    store = FileStore(tmp_path)
    task_changes = tmp_path / ".agentboard" / "goals" / gid / "tasks" / tid / "changes"
    task_changes.mkdir(parents=True)

    diff1 = """diff --git a/src/foo.py b/src/foo.py
--- a/src/foo.py
+++ b/src/foo.py
@@ -1 +1 @@
-old
+new
"""
    (task_changes / "iter_1.diff").write_text(diff1, encoding="utf-8")
    store.write_iter_artifact(rid, 1, {
        "phase": "tdd_red", "iter_n": 1,
        "diff_ref": "changes/iter_1.diff",
        "per_file_scrubber_delta": {"src/foo.py": "tdd_red"},
    }, gid=gid, tid=tid)

    store.write_iter_artifact(rid, 2, {
        "phase": "tdd_green", "iter_n": 2,
        "diff_ref": "changes/iter_1.diff",
        "per_file_scrubber_delta": {"src/foo.py": "tdd_green"},
    }, gid=gid, tid=tid)

    DigestWriter(store).update(rid)

    # Also seed the run jsonl so _resolve_rid works
    runs_dir = tmp_path / ".agentboard" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{rid}.jsonl").write_text(
        json.dumps({"event": "run_start", "task_id": tid}) + "\n",
        encoding="utf-8",
    )


class _Host(App):
    def __init__(self, tmp_path: Path, task_id: str) -> None:
        super().__init__()
        self._tmp_path = tmp_path
        self._task_id = task_id

    def compose(self) -> ComposeResult:
        from agentboard.tui.phase_flow import PhaseFlowView
        from agentboard.tui.session_derive import SessionContext
        session = SessionContext(self._tmp_path)
        yield PhaseFlowView(session, task_id=self._task_id, id="phase-flow")


async def test_dev_tab_yields_perfilescrubber(tmp_path) -> None:
    """c_001: Dev tab compose yields PerFileScrubber widget."""
    from agentboard.tui.per_file_scrubber import PerFileScrubber
    from agentboard.tui.phase_flow import PhaseFlowView

    tid = "t_c1"
    rid = "run_c1"
    gid = "g_c1"
    _seed_pile_with_scrubber(tmp_path, rid, tid, gid)

    app = _Host(tmp_path, tid)
    async with app.run_test() as pilot:
        pf = app.query_one("#phase-flow", PhaseFlowView)
        pf.action_activate_tab("dev")
        await pilot.pause()
        scrubbers = app.query("#dev-scrubber")
        assert len(scrubbers) == 1, "dev-scrubber widget not found in Dev tab"
        assert isinstance(scrubbers.first(), PerFileScrubber)


async def test_scrubber_populated_from_digest_on_mount(tmp_path) -> None:
    """c_002: Dev tab scrubber contains phases from digest first file."""
    from agentboard.tui.per_file_scrubber import PerFileScrubber
    from agentboard.tui.phase_flow import PhaseFlowView

    tid = "t_c2"
    rid = "run_c2"
    gid = "g_c2"
    _seed_pile_with_scrubber(tmp_path, rid, tid, gid)

    app = _Host(tmp_path, tid)
    async with app.run_test() as pilot:
        pf = app.query_one("#phase-flow", PhaseFlowView)
        pf.action_activate_tab("dev")
        await pilot.pause()

        scrub = app.query_one("#dev-scrubber", PerFileScrubber)
        # After mount, scrubber should have phases populated from digest
        assert scrub._phases == ["tdd_red", "tdd_green"], (
            f"scrubber phases not populated: got {scrub._phases!r}"
        )
        assert scrub._file_path == "src/foo.py"


async def test_on_scrubber_segment_clicked_opens_drawer(tmp_path) -> None:
    """c_003: handler opens DrawerContainer with iter_diff_for_file content."""
    from agentboard.tui.inline_drawer import DrawerContainer
    from agentboard.tui.per_file_scrubber import ScrubberSegmentClicked
    from agentboard.tui.phase_flow import PhaseFlowView

    tid = "t_c3"
    rid = "run_c3"
    gid = "g_c3"
    _seed_pile_with_scrubber(tmp_path, rid, tid, gid)

    app = _Host(tmp_path, tid)
    async with app.run_test() as pilot:
        pf = app.query_one("#phase-flow", PhaseFlowView)
        pf.action_activate_tab("dev")
        await pilot.pause()

        # Post the message directly instead of relying on a real click coord
        pf.post_message(ScrubberSegmentClicked(file_path="src/foo.py", iter_n=1))
        await pilot.pause()
        await pilot.pause()  # second pause for mount worker

        drawer = app.query_one("#dev-drawer", DrawerContainer)
        # Drawer should now have content
        assert drawer._active is not None, "drawer did not open on click"


async def test_drawer_content_scrollable(tmp_path) -> None:
    """c_004: drawer content wrapped in VerticalScroll so long diffs scroll."""
    from agentboard.tui.inline_drawer import DrawerContainer
    from agentboard.tui.per_file_scrubber import ScrubberSegmentClicked
    from agentboard.tui.phase_flow import PhaseFlowView

    tid = "t_c4"
    rid = "run_c4"
    gid = "g_c4"
    _seed_pile_with_scrubber(tmp_path, rid, tid, gid)

    app = _Host(tmp_path, tid)
    async with app.run_test() as pilot:
        pf = app.query_one("#phase-flow", PhaseFlowView)
        pf.action_activate_tab("dev")
        await pilot.pause()
        pf.post_message(ScrubberSegmentClicked(file_path="src/foo.py", iter_n=1))
        await pilot.pause()
        await pilot.pause()

        drawer = app.query_one("#dev-drawer", DrawerContainer)
        # Verify VerticalScroll in the drawer subtree
        scrolls = drawer.query(VerticalScroll)
        assert len(scrolls) >= 1, "drawer content not wrapped in VerticalScroll"


async def test_pilot_smoke_click_then_close(tmp_path) -> None:
    """c_005: smoke — post click message → drawer opens → direct close() works."""
    from agentboard.tui.inline_drawer import DrawerContainer
    from agentboard.tui.per_file_scrubber import ScrubberSegmentClicked
    from agentboard.tui.phase_flow import PhaseFlowView

    tid = "t_c5"
    rid = "run_c5"
    gid = "g_c5"
    _seed_pile_with_scrubber(tmp_path, rid, tid, gid)

    app = _Host(tmp_path, tid)
    async with app.run_test() as pilot:
        pf = app.query_one("#phase-flow", PhaseFlowView)
        pf.action_activate_tab("dev")
        await pilot.pause()

        pf.post_message(ScrubberSegmentClicked(file_path="src/foo.py", iter_n=1))
        await pilot.pause()
        await pilot.pause()

        drawer = app.query_one("#dev-drawer", DrawerContainer)
        assert drawer._active is not None

        await drawer.close()
        await pilot.pause()
        assert drawer._active is None, "drawer did not close"
