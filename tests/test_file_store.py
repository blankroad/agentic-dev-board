from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentboard.storage.file_store import _sanitize_id

from agentboard.models import BoardState, Goal, GoalStatus, LockedPlan, Task, TaskStatus, Iteration, ReviewVerdict
from agentboard.storage.file_store import FileStore


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


def test_save_brainstorm_accepts_optional_scope_mode(store: FileStore) -> None:
    """F4 s_001: save_brainstorm accepts scope_mode kwarg without TypeError."""
    goal = Goal(title="Scope mode brainstorm")
    store.save_goal(goal)

    store.save_brainstorm(
        goal_id=goal.id,
        premises=["p1"],
        risks=["r1"],
        alternatives=["a1"],
        existing_code_notes="notes",
        scope_mode="HOLD",
    )

    bs_path = store._goals_dir(goal.id) / "brainstorm.md"
    assert bs_path.exists()
    content = bs_path.read_text()
    assert "scope_mode: HOLD" in content


def test_save_brainstorm_accepts_structured_payload(store: FileStore) -> None:
    """F4 s_002: save_brainstorm accepts all structured kwargs."""
    goal = Goal(title="Structured payload brainstorm")
    store.save_goal(goal)

    store.save_brainstorm(
        goal_id=goal.id,
        premises=["p1"],
        risks=["r1"],
        alternatives=["a1"],
        existing_code_notes="notes",
        scope_mode="REDUCE",
        refined_goal="Do the minimum viable thing in CLI",
        wedge="One command prints JSON to stdout",
        req_list=[
            {"id": "R1", "text": "CLI command", "status": "in_scope"},
            {"id": "R2", "text": "HTML report", "status": "deferred"},
        ],
        alternatives_considered=[
            {"name": "ideal", "summary": "full platform", "chosen": False},
            {"name": "realistic", "summary": "CLI dump", "chosen": True},
        ],
        rationale="1-week buildable wedge with testable success",
        user_confirmed=True,
    )

    bs_path = store._goals_dir(goal.id) / "brainstorm.md"
    content = bs_path.read_text()
    assert "scope_mode: REDUCE" in content
    assert "refined_goal:" in content
    assert "Do the minimum viable thing in CLI" in content
    assert "wedge:" in content
    assert "req_list:" in content
    assert "R1" in content
    assert "alternatives_considered:" in content
    assert "rationale:" in content
    assert "user_confirmed: true" in content


def test_save_brainstorm_emits_yaml_frontmatter(store: FileStore) -> None:
    """F4 s_003: emitted brainstorm.md has YAML frontmatter block above prose body."""
    import frontmatter as fm_lib
    goal = Goal(title="Frontmatter parseable")
    store.save_goal(goal)

    store.save_brainstorm(
        goal_id=goal.id,
        premises=["p"],
        risks=["r"],
        alternatives=["a"],
        existing_code_notes="n",
        scope_mode="HOLD",
        refined_goal="goal X",
    )

    bs_path = store._goals_dir(goal.id) / "brainstorm.md"
    post = fm_lib.load(str(bs_path))
    assert post.metadata["scope_mode"] == "HOLD"
    assert post.metadata["refined_goal"] == "goal X"
    assert post.metadata["goal_id"] == goal.id
    assert "## Premises" in post.content


def test_save_brainstorm_legacy_format_unchanged(store: FileStore) -> None:
    """F4 s_004: legacy 4-arg call produces frontmatter with only goal_id + ts (backward compat)."""
    import frontmatter as fm_lib
    goal = Goal(title="Legacy format")
    store.save_goal(goal)

    store.save_brainstorm(
        goal_id=goal.id,
        premises=["p"],
        risks=["r"],
        alternatives=["a"],
        existing_code_notes="n",
    )

    bs_path = store._goals_dir(goal.id) / "brainstorm.md"
    post = fm_lib.load(str(bs_path))
    # only legacy fields present in frontmatter
    assert set(post.metadata.keys()) == {"goal_id", "ts"}
    assert "scope_mode" not in post.metadata
    assert "refined_goal" not in post.metadata


def test_phases_snapshot_matrix_per_goal(tmp_path) -> None:
    """C2: phases_snapshot(project_root) returns a goals-by-phases matrix.
    Each cell = one of {NOT_STARTED, RUNNING, COMPLETED, BLOCKED}. Used by
    the TUI phases tab + cross-agent phase comparison dashboards."""
    from agentboard.models import BoardState, Task, DecisionEntry
    from agentboard.analytics.phases_snapshot import phases_snapshot

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()

    g1 = Goal(title="G1 all done")
    g2 = Goal(title="G2 at frame")
    g3 = Goal(title="G3 fresh")
    store.save_goal(g1)
    store.save_goal(g2)
    store.save_goal(g3)
    for g in (g1, g2, g3):
        t = Task(goal_id=g.id, title="T")
        store.save_task(t)
        g.task_ids.append(t.id)
        store.save_goal(g)
    board = BoardState()
    board.goals.extend([g1, g2, g3])
    store.save_board(board)

    # G1: full chain completed through lock
    t1 = g1.task_ids[0]
    for phase in ["intent", "frame", "architecture", "stress", "lock"]:
        store.append_decision(t1, DecisionEntry(
            iter=0, phase=phase, reasoning=f"{phase} done", verdict_source="COMPLETED",
        ))

    # G2: only intent completed
    t2 = g2.task_ids[0]
    store.append_decision(t2, DecisionEntry(
        iter=0, phase="intent", reasoning="committed", verdict_source="COMMITTED",
    ))

    # G3: no decisions — fresh goal

    snapshot = phases_snapshot(tmp_path)
    # snapshot must be a dict with goals list
    assert "goals" in snapshot
    goals_by_id = {g["id"]: g for g in snapshot["goals"]}
    assert g1.id in goals_by_id
    assert g2.id in goals_by_id
    assert g3.id in goals_by_id

    assert goals_by_id[g1.id]["phases"]["intent"] == "COMPLETED"
    assert goals_by_id[g1.id]["phases"]["lock"] == "COMPLETED"
    assert goals_by_id[g2.id]["phases"]["intent"] == "COMPLETED"
    assert goals_by_id[g2.id]["phases"]["frame"] == "NOT_STARTED"
    assert goals_by_id[g3.id]["phases"]["intent"] == "NOT_STARTED"


def test_list_phase_events_returns_events_across_goal_tasks(store: FileStore) -> None:
    """C1: list_phase_events(goal_id) aggregates phase-boundary entries
    from decisions.jsonl across every task under the goal. Used by TUI
    phases tab + retro dashboards."""
    from agentboard.models import BoardState, Task, DecisionEntry

    goal = Goal(title="Phase events test")
    store.save_goal(goal)
    task = Task(goal_id=goal.id, title="T1")
    store.save_task(task)
    goal.task_ids.append(task.id)
    store.save_goal(goal)
    # append_decision uses load_board → _find_goal_for_task, so we need
    # the goal to be registered in state.json, not just goal.json.
    board = BoardState()
    board.goals.append(goal)
    store.save_board(board)

    # Mix of phase-boundary + per-iter entries
    store.append_decision(task.id, DecisionEntry(
        iter=0, phase="intent", reasoning="phase_start",
        verdict_source="PHASE_START",
    ))
    store.append_decision(task.id, DecisionEntry(
        iter=0, phase="intent", reasoning="scope_mode=HOLD",
        verdict_source="COMMITTED",
    ))
    store.append_decision(task.id, DecisionEntry(
        iter=1, phase="tdd_red", reasoning="RED test written",
        verdict_source="RED_CONFIRMED",
    ))
    store.append_decision(task.id, DecisionEntry(
        iter=3, phase="execute", reasoning="phase_end — 3 iters",
        verdict_source="PHASE_END",
    ))

    events = store.list_phase_events(goal.id)
    # Phase-boundary filter: PHASE_START / PHASE_END / PHASE_ABORT / terminal verdicts
    verdicts = [e["verdict_source"] for e in events]
    assert "PHASE_START" in verdicts
    assert "PHASE_END" in verdicts
    assert "COMMITTED" in verdicts
    # Per-cycle entries (RED_CONFIRMED) are NOT phase events — they're iter-level
    assert "RED_CONFIRMED" not in verdicts
    # Each event has required fields
    for ev in events:
        assert "phase" in ev
        assert "task_id" in ev
        assert "iter" in ev
        assert "verdict_source" in ev


def test_save_brainstorm_alias_consistent_under_concurrency(store: FileStore) -> None:
    """B0 (redteam HIGH): concurrent save_brainstorm must not leave the brainstorm.md
    alias pointing at an older body than the newest brainstorm-{ts}.md versioned file.

    Without the file_lock fix, atomic_write on versioned + alias can interleave across
    threads: thread A writes versioned-7, thread B writes versioned-9, thread A writes
    alias with content-7 → alias points to content-7 but latest versioned is content-9.
    """
    import concurrent.futures
    import threading

    goal = Goal(title="Concurrency test")
    store.save_goal(goal)

    barrier = threading.Barrier(20)

    def _write(n: int) -> str:
        marker = f"PREMISE-{n:02d}"
        barrier.wait()
        store.save_brainstorm(
            goal_id=goal.id,
            premises=[marker],
            risks=[],
            alternatives=[],
            existing_code_notes="",
        )
        return marker

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(_write, n) for n in range(20)]
        markers = [f.result() for f in futures]

    d = store._goals_dir(goal.id)
    versioned = sorted(d.glob("brainstorm-*.md"))
    alias = d / "brainstorm.md"
    assert len(versioned) == 20
    assert alias.exists()

    alias_body = alias.read_text()
    # pick the versioned file with the lexically latest timestamp
    latest_versioned_body = versioned[-1].read_text()
    assert alias_body == latest_versioned_body, (
        "alias diverged from the latest versioned file — "
        f"alias markers={[m for m in markers if m in alias_body]}, "
        f"latest versioned markers={[m for m in markers if m in latest_versioned_body]}"
    )


def test_save_brainstorm_validates_req_list_shape(store: FileStore) -> None:
    """H0 (redteam MEDIUM): req_list items must be dicts with id + text.
    Before the fix, None / strings / arbitrary dicts passed through."""
    goal = Goal(title="req_list validation")
    store.save_goal(goal)

    # Non-dict items
    with pytest.raises(ValueError, match="req_list"):
        store.save_brainstorm(
            goal_id=goal.id, premises=["p"], risks=[], alternatives=[],
            existing_code_notes="",
            req_list=["R1 string", "R2 string"],
        )
    with pytest.raises(ValueError, match="req_list"):
        store.save_brainstorm(
            goal_id=goal.id, premises=["p"], risks=[], alternatives=[],
            existing_code_notes="",
            req_list=[None, {"id": "R1", "text": "x", "status": "in_scope"}],
        )
    # Dict missing required keys
    with pytest.raises(ValueError, match="req_list"):
        store.save_brainstorm(
            goal_id=goal.id, premises=["p"], risks=[], alternatives=[],
            existing_code_notes="",
            req_list=[{"only_id": "R1"}],
        )


def test_save_brainstorm_validates_scope_mode_enum(store: FileStore) -> None:
    """H0 (redteam MEDIUM): scope_mode must be one of EXPAND / SELECTIVE /
    HOLD / REDUCE. MCP schema enum is best-effort; direct Python callers
    bypass it. Validate server-side."""
    goal = Goal(title="scope_mode validation")
    store.save_goal(goal)

    with pytest.raises(ValueError, match="scope_mode"):
        store.save_brainstorm(
            goal_id=goal.id, premises=["p"], risks=[], alternatives=[],
            existing_code_notes="",
            scope_mode="INVALID_MODE",
        )
    with pytest.raises(ValueError, match="scope_mode"):
        store.save_brainstorm(
            goal_id=goal.id, premises=["p"], risks=[], alternatives=[],
            existing_code_notes="",
            scope_mode="",
        )


def test_save_brainstorm_chosen_must_be_boolean(store: FileStore) -> None:
    """H0 (redteam MEDIUM): alternatives_considered[i].chosen must be a
    bool. `is True` correctly rejects string 'true', but that's silent —
    turn it into an explicit ValueError so bad transport serialization
    surfaces loudly."""
    goal = Goal(title="chosen type validation")
    store.save_goal(goal)

    with pytest.raises(ValueError, match="chosen"):
        store.save_brainstorm(
            goal_id=goal.id, premises=["p"], risks=[], alternatives=[],
            existing_code_notes="",
            alternatives_considered=[
                {"name": "A", "chosen": "true"},  # string, not bool
                {"name": "B", "chosen": False},
            ],
        )


def test_save_brainstorm_rejects_non_dict_alternatives(store: FileStore) -> None:
    """F4 redteam HIGH: non-dict items in alternatives_considered must raise ValueError,
    not AttributeError. MCP dispatch only catches ValueError."""
    goal = Goal(title="Non-dict alternatives")
    store.save_goal(goal)

    with pytest.raises(ValueError, match="alternatives_considered"):
        store.save_brainstorm(
            goal_id=goal.id,
            premises=["p"],
            risks=["r"],
            alternatives=["a"],
            existing_code_notes="n",
            alternatives_considered=["not a dict", {"name": "B", "chosen": True}],
        )


def test_save_brainstorm_validates_chosen_uniqueness(store: FileStore) -> None:
    """F4 s_005: save_brainstorm raises ValueError on 0 or >=2 chosen:true in alternatives_considered."""
    goal = Goal(title="Chosen validation")
    store.save_goal(goal)

    # zero chosen
    with pytest.raises(ValueError, match="exactly one alternative"):
        store.save_brainstorm(
            goal_id=goal.id,
            premises=["p"],
            risks=["r"],
            alternatives=["a"],
            existing_code_notes="n",
            alternatives_considered=[
                {"name": "A", "chosen": False},
                {"name": "B", "chosen": False},
            ],
        )

    # two chosen
    with pytest.raises(ValueError, match="exactly one alternative"):
        store.save_brainstorm(
            goal_id=goal.id,
            premises=["p"],
            risks=["r"],
            alternatives=["a"],
            existing_code_notes="n",
            alternatives_considered=[
                {"name": "A", "chosen": True},
                {"name": "B", "chosen": True},
            ],
        )
