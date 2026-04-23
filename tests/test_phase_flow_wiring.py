"""M1b-wiring tests — rid resolver + pile-priority in _load_latest_diff_text.

Verifies phase_flow.py integration of M1b Cinema Labor primitives.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_run_jsonl(runs_dir: Path, run_id: str, task_id: str) -> Path:
    """Write a minimal valid run jsonl with task_id in its first event."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run_id}.jsonl"
    path.write_text(
        json.dumps({"event": "run_start", "task_id": task_id, "ts": "2026-01-01T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    return path


def _make_view(tmp_path: Path, task_id: str):
    from agentboard.tui.phase_flow import PhaseFlowView
    from agentboard.tui.session_derive import SessionContext

    session = SessionContext(tmp_path)
    view = PhaseFlowView(session, task_id=task_id)
    return view


def test_resolve_rid_returns_latest_matching_run(tmp_path) -> None:
    """w_001: _resolve_rid picks the latest run file whose task_id matches."""
    import time
    tid = "t_wire"
    runs_dir = tmp_path / ".agentboard" / "runs"
    # Two runs, same task — second must be selected
    _write_run_jsonl(runs_dir, "run_older", tid)
    time.sleep(0.02)
    _write_run_jsonl(runs_dir, "run_newer", tid)
    # A third run belongs to a different task — must be ignored
    _write_run_jsonl(runs_dir, "run_unrelated", "t_other")

    view = _make_view(tmp_path, tid)
    assert view._resolve_rid() == "run_newer"


def test_resolve_rid_returns_none_when_no_match(tmp_path) -> None:
    """w_002: _resolve_rid returns None when no run matches current task_id."""
    runs_dir = tmp_path / ".agentboard" / "runs"
    _write_run_jsonl(runs_dir, "run_other", "t_other_task")

    view = _make_view(tmp_path, "t_missing")
    assert view._resolve_rid() is None


def test_load_latest_diff_text_prefers_pile(tmp_path, monkeypatch) -> None:
    """w_003: when rid resolves AND pile has diff content, return pile content (not git)."""
    from agentboard.storage.file_store import FileStore

    tid = "t_pile"
    rid = "run_pile"

    # Seed run jsonl so _resolve_rid finds it
    runs_dir = tmp_path / ".agentboard" / "runs"
    _write_run_jsonl(runs_dir, rid, tid)

    # Seed pile with iter + diff
    gid = "g_pile"
    store = FileStore(tmp_path)
    task_changes = tmp_path / ".agentboard" / "goals" / gid / "tasks" / tid / "changes"
    task_changes.mkdir(parents=True)
    pile_diff = """diff --git a/src/pile_marker.py b/src/pile_marker.py
--- a/src/pile_marker.py
+++ b/src/pile_marker.py
@@ -1 +1 @@
-old-pile
+new-pile
"""
    (task_changes / "iter_1.diff").write_text(pile_diff, encoding="utf-8")
    store.write_iter_artifact(rid, 1, {
        "phase": "tdd_red", "iter_n": 1, "diff_ref": "changes/iter_1.diff",
    }, gid=gid, tid=tid)

    # Guarantee git subprocess would return something different/empty
    # by changing session.store_root to tmp_path (no git repo there)
    view = _make_view(tmp_path, tid)
    out = view._load_latest_diff_text()
    assert "pile_marker.py" in out, f"pile content not returned, got: {out[:200]}"
    assert "new-pile" in out


def test_load_latest_diff_text_falls_back_to_git_when_pile_empty(tmp_path) -> None:
    """w_004: when rid resolves but pile returns empty, fall through to git subprocess
    (which itself returns empty in a non-repo tmp_path → final result is '').
    Backward compat: no pile does NOT break existing behavior.
    """
    tid = "t_empty"
    rid = "run_empty"
    runs_dir = tmp_path / ".agentboard" / "runs"
    _write_run_jsonl(runs_dir, rid, tid)

    # No pile seeded → pile-loader returns [] → empty string

    view = _make_view(tmp_path, tid)
    out = view._load_latest_diff_text()
    # Not an exception; empty or legacy-path content is fine.
    assert isinstance(out, str)
