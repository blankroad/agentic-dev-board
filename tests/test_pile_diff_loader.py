"""pile_diff_loader tests (M1b m_002, m_003, m_004)."""
from __future__ import annotations

import json


_DIFF_FILE_A = """diff --git a/src/foo.py b/src/foo.py
index 111..222 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,3 +1,4 @@
 def foo():
-    return 1
+    return 2
+    # added
"""

_DIFF_FILE_AB = """diff --git a/src/foo.py b/src/foo.py
index 222..333 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,4 +1,5 @@
 def foo():
     return 2
     # added
+    # iter 2 added more
diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null
+++ b/src/bar.py
@@ -0,0 +1,2 @@
+def bar():
+    pass
"""


def _seed_pile_with_diffs(tmp_path, rid: str, gid: str, tid: str) -> None:
    from agentboard.storage.file_store import FileStore
    store = FileStore(tmp_path)
    # Seed task dir for changes/ helper path
    task_changes = tmp_path / ".devboard" / "goals" / gid / "tasks" / tid / "changes"
    task_changes.mkdir(parents=True)
    # iter 1: modifies foo.py only
    (task_changes / "iter_1.diff").write_text(_DIFF_FILE_A, encoding="utf-8")
    store.write_iter_artifact(rid, 1, {
        "phase": "tdd_red", "iter_n": 1,
        "diff_ref": f"changes/iter_1.diff",  # task-relative
    }, gid=gid, tid=tid)
    # iter 2: modifies foo.py again + adds bar.py
    (task_changes / "iter_2.diff").write_text(_DIFF_FILE_AB, encoding="utf-8")
    store.write_iter_artifact(rid, 2, {
        "phase": "tdd_green", "iter_n": 2,
        "diff_ref": f"changes/iter_2.diff",
    }, gid=gid, tid=tid)


def test_load_files_from_pile_aggregates_across_iters(tmp_path) -> None:
    """m_002: load_files_from_pile returns unique DiffFile records aggregated
    across all iter.json + their referenced diff files.
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_diff_loader import load_files_from_pile

    rid, gid, tid = "run_pdl", "g_pdl", "t_pdl"
    _seed_pile_with_diffs(tmp_path, rid, gid, tid)

    store = FileStore(tmp_path)
    files = load_files_from_pile(rid, store)
    paths = {f.path for f in files}
    assert "src/foo.py" in paths
    assert "src/bar.py" in paths
    assert len(files) == 2  # deduped


def test_final_diff_for_file_concatenates_iter_slices(tmp_path) -> None:
    """m_003: final_diff_for_file returns concatenated per-iter diff slices
    for the requested path.
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_diff_loader import final_diff_for_file

    rid, gid, tid = "run_fd", "g_fd", "t_fd"
    _seed_pile_with_diffs(tmp_path, rid, gid, tid)

    store = FileStore(tmp_path)
    diff = final_diff_for_file(rid, "src/foo.py", store)
    # Should include hunks from BOTH iter 1 and iter 2 (foo.py touched twice)
    assert "return 2" in diff  # from iter 1
    assert "iter 2 added more" in diff  # from iter 2

    # bar.py only in iter 2
    bar_diff = final_diff_for_file(rid, "src/bar.py", store)
    assert "def bar():" in bar_diff


def test_iter_diff_for_file_single_iter_slice(tmp_path) -> None:
    """m_004: iter_diff_for_file returns just the named iter's slice for
    the requested file (drawer payload).
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_diff_loader import iter_diff_for_file

    rid, gid, tid = "run_id", "g_id", "t_id"
    _seed_pile_with_diffs(tmp_path, rid, gid, tid)

    store = FileStore(tmp_path)
    # iter 1 of foo.py: should NOT contain "iter 2 added more"
    iter1 = iter_diff_for_file(rid, "src/foo.py", 1, store)
    assert "return 2" in iter1
    assert "iter 2 added more" not in iter1

    # iter 2 of foo.py: should contain "iter 2 added more" but not bar.py
    iter2 = iter_diff_for_file(rid, "src/foo.py", 2, store)
    assert "iter 2 added more" in iter2
    assert "def bar():" not in iter2
