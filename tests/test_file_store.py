from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from devboard.storage.file_store import _sanitize_id

from devboard.models import BoardState, Goal, GoalStatus, LockedPlan, Task, TaskStatus, Iteration, ReviewVerdict
from devboard.storage.file_store import FileStore


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    s = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    return s


def test_board_roundtrip(store: FileStore) -> None:
    board = BoardState()
    store.save_board(board)
    loaded = store.load_board()
    assert loaded.board_id == board.board_id
    assert loaded.version == 1


def test_board_empty_returns_default(store: FileStore) -> None:
    board = store.load_board()
    assert isinstance(board, BoardState)
    assert board.goals == []


def test_goal_roundtrip(store: FileStore) -> None:
    goal = Goal(title="Add calculator", description="With div-by-zero handling")
    store.save_goal(goal)

    loaded = store.load_goal(goal.id)
    assert loaded is not None
    assert loaded.title == goal.title
    assert loaded.description == goal.description
    assert loaded.status == GoalStatus.active


def test_goal_not_found(store: FileStore) -> None:
    assert store.load_goal("g_nonexistent") is None


def test_task_roundtrip(store: FileStore) -> None:
    goal = Goal(title="Test goal")
    store.save_goal(goal)

    task = Task(
        goal_id=goal.id,
        title="Implement feature",
        description="Details here",
        touches=["src/feature.py"],
        forbids=["src/payments/"],
    )
    store.save_task(task)

    loaded = store.load_task(goal.id, task.id)
    assert loaded is not None
    assert loaded.title == task.title
    assert loaded.touches == ["src/feature.py"]
    assert loaded.forbids == ["src/payments/"]


def test_task_creates_markdown(store: FileStore) -> None:
    goal = Goal(title="Test goal")
    store.save_goal(goal)

    task = Task(goal_id=goal.id, title="My Task", description="desc")
    store.save_task(task)

    md_path = store._tasks_dir(goal.id, task.id) / "task.md"
    assert md_path.exists()
    content = md_path.read_text()
    assert "My Task" in content
    assert task.id in content


def test_task_with_iterations(store: FileStore) -> None:
    goal = Goal(title="Goal with iters")
    store.save_goal(goal)

    task = Task(goal_id=goal.id, title="Iterative task")
    task.iterations.append(Iteration(
        number=1,
        plan_summary="initial plan",
        test_report="3/5 passing",
        review_verdict=ReviewVerdict.retry,
        review_notes="missing error handler",
        reflect_reasoning="focus on error branch",
    ))
    task.iterations.append(Iteration(
        number=2,
        plan_summary="fix error branch",
        test_report="5/5 passing",
        review_verdict=ReviewVerdict.pass_,
        review_notes="all good",
    ))
    store.save_task(task)

    loaded = store.load_task(goal.id, task.id)
    assert loaded is not None
    assert len(loaded.iterations) == 2
    assert loaded.iterations[0].review_verdict == ReviewVerdict.retry
    assert loaded.iterations[1].review_verdict == ReviewVerdict.pass_

    md_path = store._tasks_dir(goal.id, task.id) / "task.md"
    content = md_path.read_text()
    assert "Iteration 1" in content
    assert "Iteration 2" in content
    assert "initial plan" in content


def test_locked_plan_roundtrip(store: FileStore) -> None:
    goal = Goal(title="Goal with plan")
    store.save_goal(goal)

    plan = LockedPlan(
        goal_id=goal.id,
        problem="Need a calculator",
        non_goals=["GUI", "scientific ops"],
        scope_decision="hold scope",
        architecture="simple functions module",
        known_failure_modes=["div-by-zero", "type errors"],
        goal_checklist=["add/sub/mul/div impl", "pytest coverage"],
        out_of_scope_guard=["src/payments/"],
        token_ceiling=100_000,
        max_iterations=5,
    ).lock()

    store.save_locked_plan(plan)

    loaded = store.load_locked_plan(goal.id)
    assert loaded is not None
    assert loaded.problem == plan.problem
    assert loaded.locked_hash == plan.locked_hash
    assert loaded.goal_checklist == plan.goal_checklist
    assert loaded.token_ceiling == 100_000


def test_locked_plan_creates_markdown(store: FileStore) -> None:
    goal = Goal(title="Plan md goal")
    store.save_goal(goal)

    plan = LockedPlan(
        goal_id=goal.id,
        problem="Build X",
        goal_checklist=["item 1", "item 2"],
    ).lock()
    store.save_locked_plan(plan)

    md_path = store._goals_dir(goal.id) / "plan.md"
    assert md_path.exists()
    content = md_path.read_text()
    assert "item 1" in content
    assert "item 2" in content
    assert plan.locked_hash in content


def test_save_iter_diff(store: FileStore) -> None:
    board = BoardState()
    goal = Goal(title="Diff goal")
    task = Task(goal_id=goal.id, title="Diff task")
    goal.task_ids.append(task.id)
    board.goals.append(goal)
    store.save_board(board)
    store.save_goal(goal)
    store.save_task(task)

    diff = "+++ new line\n--- old line\n"
    store.save_iter_diff(task.id, 1, diff)

    diff_path = store._tasks_dir(goal.id, task.id) / "changes" / "iter_1.diff"
    assert diff_path.exists()
    assert diff_path.read_text() == diff


def test_append_decision(store: FileStore) -> None:
    board = BoardState()
    goal = Goal(title="Decision goal")
    task = Task(goal_id=goal.id, title="Decision task")
    goal.task_ids.append(task.id)
    board.goals.append(goal)
    store.save_board(board)
    store.save_goal(goal)
    store.save_task(task)

    entry = {"iter": 1, "phase": "reflect", "reasoning": "test failed", "ts": datetime.now(timezone.utc).isoformat()}
    store.append_decision(task.id, entry)

    jsonl_path = store._tasks_dir(goal.id, task.id) / "decisions.jsonl"
    assert jsonl_path.exists()
    line = json.loads(jsonl_path.read_text().strip())
    assert line["iter"] == 1
    assert line["reasoning"] == "test failed"


def test_gauntlet_step_saved(store: FileStore) -> None:
    goal = Goal(title="Gauntlet goal")
    store.save_goal(goal)

    content = "## Frame\nThis is the problem statement."
    store.save_gauntlet_step(goal.id, "frame", content)

    step_path = store._goals_dir(goal.id) / "gauntlet" / "frame.md"
    assert step_path.exists()
    assert step_path.read_text() == content


def test_locked_plan_hash_stability(store: FileStore) -> None:
    goal = Goal(title="Hash test")
    store.save_goal(goal)

    plan = LockedPlan(goal_id=goal.id, problem="same problem", goal_checklist=["a", "b"]).lock()
    h1 = plan.locked_hash

    plan2 = LockedPlan(goal_id=goal.id, problem="same problem", goal_checklist=["a", "b"]).lock()
    assert plan2.locked_hash == h1

    plan3 = LockedPlan(goal_id=goal.id, problem="different problem", goal_checklist=["a", "b"]).lock()
    assert plan3.locked_hash != h1


def test_run_events(store: FileStore) -> None:
    event = {"node": "plan", "iter": 1, "ts": datetime.now(timezone.utc).isoformat()}
    store.append_run_event("run_001", event)
    store.append_run_event("run_001", {"node": "impl", "iter": 1, "ts": datetime.now(timezone.utc).isoformat()})

    events = store.load_run_events("run_001")
    assert len(events) == 2
    assert events[0]["node"] == "plan"
    assert events[1]["node"] == "impl"


# ── _sanitize_id ──────────────────────────────────────────────────────────────

def test_sanitize_id_valid_passes_through():
    assert _sanitize_id("g_abc") == "g_abc"


def test_sanitize_id_traversal_raises():
    with pytest.raises(ValueError):
        _sanitize_id("../../etc")


def test_sanitize_id_existing_goal_id_format():
    """g_{date}_{time}_{hex} format must pass — existing .devboard dirs use this."""
    assert _sanitize_id("g_20260418_014050_0ecfaa") == "g_20260418_014050_0ecfaa"


# ── save_brainstorm ───────────────────────────────────────────────────────────

def test_save_brainstorm_writes_correct_format(store: FileStore) -> None:
    goal = Goal(title="Brainstorm goal")
    store.save_goal(goal)

    store.save_brainstorm(
        goal_id=goal.id,
        premises=["Users need X", "Current system lacks Y"],
        risks=["Scope creep", "Breaking change"],
        alternatives=["Option A", "Option B"],
        existing_code_notes="See file_store.py:save_goal",
    )

    bs_path = store._goals_dir(goal.id) / "brainstorm.md"
    assert bs_path.exists()
    content = bs_path.read_text()

    assert f"goal_id: {goal.id}" in content
    assert "## Premises" in content
    assert "- Users need X" in content
    assert "- Scope creep" in content
    assert "## Risks" in content
    assert "## Alternatives" in content
    assert "- Option A" in content
    assert "## Existing Code Notes" in content
    assert "See file_store.py:save_goal" in content


# ── save_plan_review / load_plan_review ───────────────────────────────────────

def test_save_plan_review_approved(store: FileStore) -> None:
    goal = Goal(title="Plan review goal")
    store.save_goal(goal)

    store.save_plan_review(goal_id=goal.id, approved=True)

    review_path = store._goals_dir(goal.id) / "plan_review.json"
    assert review_path.exists()
    data = json.loads(review_path.read_text())
    assert data["status"] == "approved"
    assert "ts" in data


def test_load_plan_review_returns_none_when_missing(store: FileStore) -> None:
    goal = Goal(title="No review goal")
    store.save_goal(goal)
    assert store.load_plan_review(goal.id) is None


def test_save_brainstorm_creates_versioned_file(store: FileStore) -> None:
    goal = Goal(title="Versioned brainstorm")
    store.save_goal(goal)

    store.save_brainstorm(
        goal_id=goal.id,
        premises=["p1"],
        risks=["r1"],
        alternatives=["a1"],
        existing_code_notes="notes",
    )

    d = store._goals_dir(goal.id)
    versioned = list(d.glob("brainstorm-*.md"))
    assert len(versioned) == 1
    content = versioned[0].read_text()
    assert "goal_id:" in content
    assert "## Premises" in content
