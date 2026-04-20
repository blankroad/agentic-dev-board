"""Tests for OverviewPayload builder (s_003-s_006)."""

from pathlib import Path

from devboard.analytics.overview_payload import build_overview_payload


def _fresh_goal(tmp_path: Path, gid: str = "g_test") -> Path:
    goal_dir = tmp_path / ".devboard" / "goals" / gid
    goal_dir.mkdir(parents=True)
    return goal_dir


def _task_dir(goal_dir: Path, tid: str) -> Path:
    td = goal_dir / "tasks" / tid
    (td / "changes").mkdir(parents=True)
    return td


def test_build_overview_payload_no_task(tmp_path: Path) -> None:
    """Empty goal (no task, no plan, no brainstorm) → awaiting_task state."""
    _fresh_goal(tmp_path)
    out = build_overview_payload(tmp_path, "g_test", task_id=None)
    assert out["iterations"] == []
    assert out["current_state"]["status"] == "awaiting_task"


def test_build_overview_payload_purpose_and_plan_digest(tmp_path: Path) -> None:
    """Purpose pulled from brainstorm.md premises[0]; plan_digest from plan.json."""
    gdir = _fresh_goal(tmp_path)
    (gdir / "brainstorm.md").write_text(
        "---\ngoal_id: g_test\n---\n## Premises\n- Center-panel redesign\n- users: me\n",
        encoding="utf-8",
    )
    (gdir / "plan.json").write_text(
        '{"locked_hash": "abc123", "scope_decision": "SELECTIVE", '
        '"atomic_steps": [{"id": "s_001", "completed": true}, '
        '{"id": "s_002", "completed": false}]}',
        encoding="utf-8",
    )
    out = build_overview_payload(tmp_path, "g_test", task_id=None)
    assert out["purpose"] == "Center-panel redesign"
    assert out["plan_digest"]["locked_hash"] == "abc123"
    assert out["plan_digest"]["scope_decision"] == "SELECTIVE"
    assert out["plan_digest"]["atomic_steps_done"] == 1
    assert out["plan_digest"]["atomic_steps_total"] == 2


def test_build_overview_payload_iterations_with_numstat(tmp_path: Path) -> None:
    """iterations pulls per-iter row from decisions.jsonl and numstat from changes/iter_N.diff."""
    gdir = _fresh_goal(tmp_path)
    tdir = _task_dir(gdir, "t_test")
    (tdir / "decisions.jsonl").write_text(
        '{"iter": 1, "phase": "tdd_red", "verdict_source": "RED_CONFIRMED", "ts": "2026-04-20T13:30:00"}\n'
        '{"iter": 2, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED", "ts": "2026-04-20T13:38:00"}\n',
        encoding="utf-8",
    )
    (tdir / "changes" / "iter_1.diff").write_text(
        "diff --git a/tests/x.py b/tests/x.py\n"
        "--- a/tests/x.py\n+++ b/tests/x.py\n"
        "@@ -0,0 +1,3 @@\n+a\n+b\n+c\n",
        encoding="utf-8",
    )
    (tdir / "changes" / "iter_2.diff").write_text("", encoding="utf-8")
    out = build_overview_payload(tmp_path, "g_test", task_id="t_test")
    iters = out["iterations"]
    assert len(iters) == 2
    assert iters[0]["iter"] == 1
    assert iters[0]["phase"] == "tdd_red"
    assert iters[0]["verdict"] == "RED_CONFIRMED"
    assert iters[0]["touched_files"] == ["tests/x.py"]
    assert iters[1]["iter"] == 2
    assert iters[1]["touched_files"] == []


def test_build_overview_payload_iter_prefers_green_phase(tmp_path: Path) -> None:
    """Per-iter primary row must prefer tdd_green over tdd_refactor/SKIPPED.

    Regression guard for 2026-04-20 Dev-tab noise issue: last-row-wins made every
    iter show 'tdd_refactor · SKIPPED · +0 −0 · (none)' regardless of real work.
    """
    gdir = _fresh_goal(tmp_path)
    tdir = _task_dir(gdir, "t_test")
    (tdir / "decisions.jsonl").write_text(
        '{"iter": 1, "phase": "tdd_red", "verdict_source": "RED_CONFIRMED",'
        ' "reasoning": "red reasoning", "ts": "2026-04-20T13:30:00"}\n'
        '{"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",'
        ' "reasoning": "ship iter 1 green", "ts": "2026-04-20T13:31:00"}\n'
        '{"iter": 1, "phase": "tdd_refactor", "verdict_source": "SKIPPED",'
        ' "reasoning": "no refactor.", "ts": "2026-04-20T13:31:05"}\n',
        encoding="utf-8",
    )
    out = build_overview_payload(tmp_path, "g_test", task_id="t_test")
    assert len(out["iterations"]) == 1
    row = out["iterations"][0]
    assert row["phase"] == "tdd_green"
    assert row["verdict"] == "GREEN_CONFIRMED"
    assert row["reasoning"] == "ship iter 1 green"


def test_build_overview_payload_partial_failure(tmp_path: Path) -> None:
    """Corrupt plan.json must not erase purpose — per-section try/except.

    guards: partial-failure section isolation (F3 mitigation)
    """
    gdir = _fresh_goal(tmp_path)
    (gdir / "brainstorm.md").write_text(
        "---\ngoal_id: g_test\n---\n## Premises\n- Alive purpose\n",
        encoding="utf-8",
    )
    (gdir / "plan.json").write_text("{not: valid json", encoding="utf-8")

    # Also: task with garbage decisions.jsonl should yield iterations=[] without
    # erasing purpose — exercise multiple failing sections at once.
    tdir = _task_dir(gdir, "t_test")
    (tdir / "decisions.jsonl").write_text(
        "not-json\n{also-not-json\n", encoding="utf-8"
    )
    out = build_overview_payload(tmp_path, "g_test", task_id="t_test")
    assert out["purpose"] == "Alive purpose"
    assert out["plan_digest"] == {}
    assert out["iterations"] == []
