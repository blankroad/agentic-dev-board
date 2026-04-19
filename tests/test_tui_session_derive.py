from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _write_goal(root: Path, gid: str, title: str = "", plan_text: str | None = None) -> Path:
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    devboard = root / ".devboard"
    devboard.mkdir(exist_ok=True)
    store = FileStore(root)
    try:
        board = store.load_board()
    except Exception:
        board = BoardState()
    board.goals.append(Goal(id=gid, title=title or gid, status=GoalStatus.active))
    store.save_board(board)
    goal_dir = devboard / "goals" / gid
    goal_dir.mkdir(parents=True, exist_ok=True)
    if plan_text is not None:
        (goal_dir / "plan.md").write_text(plan_text)
    return goal_dir


def test_active_goal_picks_latest_plan_mtime(tmp_path: Path) -> None:
    from devboard.tui.session_derive import SessionContext

    g1 = _write_goal(tmp_path, "g_old", plan_text="# old plan")
    g2 = _write_goal(tmp_path, "g_new", plan_text="# new plan")
    old_mtime = time.time() - 1000
    os.utime(g1 / "plan.md", (old_mtime, old_mtime))

    ctx = SessionContext(tmp_path)
    assert ctx.active_goal_id == "g_new", (
        f"should pick goal with latest plan.md mtime; got {ctx.active_goal_id!r}"
    )


def test_no_goals_returns_none_active(tmp_path: Path) -> None:
    from devboard.tui.session_derive import SessionContext

    (tmp_path / ".devboard").mkdir()
    ctx = SessionContext(tmp_path)
    assert ctx.active_goal_id is None


def test_decisions_sorted_newest_first(tmp_path: Path) -> None:
    from devboard.tui.session_derive import SessionContext

    g = _write_goal(tmp_path, "g_x", plan_text="# p")
    task_dir = g / "tasks" / "t_x"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_x", "status": "in_progress"}))
    decisions = task_dir / "decisions.jsonl"
    decisions.write_text(
        json.dumps({"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED"})
        + "\n"
        + json.dumps({"iter": 3, "phase": "redteam", "verdict_source": "BROKEN"})
        + "\n"
        + json.dumps({"iter": 2, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED"})
        + "\n"
    )

    ctx = SessionContext(tmp_path)
    rows = ctx.decisions_for_task("t_x")
    iters = [d.get("iter") for d in rows]
    assert iters == [3, 2, 1], f"decisions must sort newest iter first; got {iters}"


def test_diff_parser_strips_crlf_trailing_r(tmp_path: Path) -> None:
    """Red-team: CRLF-terminated iter_N.diff must not leak \\r into
    returned file paths (regex \\r-aware)."""
    from devboard.tui.session_derive import SessionContext

    (tmp_path / ".devboard").mkdir()
    goal_dir = tmp_path / ".devboard" / "goals" / "g_crlf"
    (goal_dir / "tasks" / "t_c" / "changes").mkdir(parents=True)
    from devboard.models import BoardState, Goal, GoalStatus
    from devboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    board = BoardState()
    board.goals.append(Goal(id="g_crlf", title="c", status=GoalStatus.active))
    store.save_board(board)
    (goal_dir / "plan.md").write_text("# p\n")
    (goal_dir / "tasks" / "t_c" / "task.json").write_text(
        json.dumps({"id": "t_c", "status": "in_progress"})
    )
    (goal_dir / "tasks" / "t_c" / "changes" / "iter_1.diff").write_bytes(
        b"+++ b/src/a.py\r\n+++ b/tests/b.py\r\n"
    )

    ctx = SessionContext(tmp_path)
    files = ctx.files_changed_in_iter("t_c", 1)
    assert files == ["src/a.py", "tests/b.py"], (
        f"CRLF must not leak into paths; got {files!r}"
    )


def test_diff_parser_extracts_touched_files(tmp_path: Path) -> None:
    from devboard.tui.session_derive import SessionContext

    g = _write_goal(tmp_path, "g_d", plan_text="# p")
    task_dir = g / "tasks" / "t_d"
    changes = task_dir / "changes"
    changes.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({"id": "t_d", "status": "in_progress"}))
    (changes / "iter_1.diff").write_text(
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1 +1,2 @@\n"
        "+hello\n"
        "diff --git a/tests/b.py b/tests/b.py\n"
        "--- a/tests/b.py\n"
        "+++ b/tests/b.py\n"
        "@@ -1 +1,2 @@\n"
        "+world\n"
    )

    ctx = SessionContext(tmp_path)
    files = ctx.files_changed_in_iter("t_d", 1)
    assert "src/a.py" in files and "tests/b.py" in files, files
    assert len(files) == 2, files
