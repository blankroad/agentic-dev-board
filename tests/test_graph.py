from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devboard.agents.reflect import _parse_reflect
from devboard.llm.client import CompletionResult
from devboard.models import Goal, BoardState, LockedPlan
from devboard.orchestrator.checkpointer import Checkpointer
from devboard.orchestrator.runner import run_loop
from devboard.storage.file_store import FileStore


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_result(text: str) -> CompletionResult:
    r = CompletionResult(
        text=text, thinking="", input_tokens=10, output_tokens=5,
        model="claude-sonnet-4-6", cached_tokens=0,
    )
    r._raw_content = []
    return r


def _make_plan(goal_id: str = "g_001") -> LockedPlan:
    from devboard.gauntlet.lock import build_locked_plan
    return build_locked_plan(goal_id, {
        "problem": "Add hello.py",
        "non_goals": [],
        "scope_decision": "HOLD",
        "architecture": "Single hello.py with greet()",
        "known_failure_modes": [],
        "goal_checklist": ["hello.py exists", "greet() returns 'Hello, World!'"],
        "out_of_scope_guard": ["src/payments/"],
        "token_ceiling": 100_000,
        "max_iterations": 3,
    })


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    s = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    return s


# ── Checkpointer ──────────────────────────────────────────────────────────────

def test_checkpointer_save_load(tmp_path: Path):
    cp = Checkpointer(tmp_path / "run.jsonl")
    cp.save("step_a", {"x": 1})
    cp.save("step_b", {"x": 2})
    entries = cp.load_all()
    assert len(entries) == 2
    assert entries[0]["event"] == "step_a"
    assert entries[1]["state"]["x"] == 2


def test_checkpointer_last_state(tmp_path: Path):
    cp = Checkpointer(tmp_path / "run.jsonl")
    cp.save("a", {"n": 1})
    cp.save("b", {"n": 2})
    assert cp.last_state() == {"n": 2}


def test_checkpointer_find_resume_point(tmp_path: Path):
    cp = Checkpointer(tmp_path / "run.jsonl")
    cp.save("iteration_complete", {"iteration": 2, "history": [{"n": 1}, {"n": 2}]})
    result = cp.find_resume_point()
    assert result is not None
    iter_n, state = result
    assert iter_n == 2


def test_checkpointer_empty(tmp_path: Path):
    cp = Checkpointer(tmp_path / "run.jsonl")
    assert cp.load_all() == []
    assert cp.last_state() is None
    assert cp.find_resume_point() is None


# ── _parse_reflect ────────────────────────────────────────────────────────────

def test_parse_reflect_valid_json():
    text = json.dumps({
        "root_cause": "missing test",
        "next_strategy": "add pytest",
        "learning": "always test",
        "risk": "LOW",
        "risk_reason": "small change",
    })
    result = _parse_reflect(text)
    assert result["root_cause"] == "missing test"
    assert result["risk"] == "LOW"


def test_parse_reflect_fenced():
    inner = json.dumps({"root_cause": "x", "next_strategy": "y", "learning": "", "risk": "MEDIUM", "risk_reason": ""})
    text = f"```json\n{inner}\n```"
    result = _parse_reflect(text)
    assert result["root_cause"] == "x"


def test_parse_reflect_fallback():
    result = _parse_reflect("This is not JSON at all.")
    assert "root_cause" in result
    assert result["risk"] == "MEDIUM"


# ── run_loop with mocked agents ───────────────────────────────────────────────

PLAN_TEXT = "## Plan\n1. Write hello.py\n2. Run pytest"
EXEC_TEXT = "## Execution Summary\nCreated hello.py"
REVIEW_PASS = "## Review\n- [x] hello.py exists\n- [x] greet() works\n\n### Verdict: PASS"
REVIEW_RETRY = "## Review\n- [x] hello.py exists\n- [ ] greet() missing\n\n### Verdict: RETRY\nAdd greet() function"
REFLECT_TEXT = json.dumps({
    "root_cause": "greet() was not implemented",
    "next_strategy": "implement greet() returning Hello, World!",
    "learning": "",
    "risk": "LOW",
    "risk_reason": "",
})


@patch("devboard.orchestrator.graph.run_planner")
@patch("devboard.orchestrator.graph.run_executor")
@patch("devboard.orchestrator.graph.run_reviewer")
@patch("devboard.orchestrator.graph._get_diff", return_value="--- a\n+++ b\n+hello.py")
@patch("devboard.orchestrator.graph._local_commit")
def test_run_loop_converges_first_try(
    mock_commit, mock_diff, mock_reviewer, mock_executor, mock_planner,
    store: FileStore, tmp_path: Path,
):
    from devboard.agents.base import AgentResult
    from devboard.agents.reviewer import ReviewVerdict

    mock_planner.return_value = AgentResult(PLAN_TEXT, [], _mock_result(PLAN_TEXT))
    mock_executor.return_value = AgentResult(EXEC_TEXT, [], _mock_result(EXEC_TEXT))
    mock_reviewer.return_value = (ReviewVerdict.pass_, AgentResult(REVIEW_PASS, [], _mock_result(REVIEW_PASS)))

    goal = Goal(title="Hello", description="Add hello.py")
    store.save_goal(goal)

    plan = _make_plan(goal.id)
    result = run_loop(
        goal_id=goal.id,
        task_id="t_001",
        goal_description=goal.description,
        locked_plan=plan,
        project_root=tmp_path,
        store=store,
        client=MagicMock(),
    )

    assert result.converged
    assert not result.blocked
    assert result.iteration == 1
    mock_commit.assert_called_once()


@patch("devboard.orchestrator.graph.run_planner")
@patch("devboard.orchestrator.graph.run_executor")
@patch("devboard.orchestrator.graph.run_reviewer")
@patch("devboard.orchestrator.graph.run_reflect")
@patch("devboard.orchestrator.graph.run_systematic_debug")
@patch("devboard.orchestrator.graph.verify_checklist")
@patch("devboard.orchestrator.graph._get_diff", return_value="")
@patch("devboard.orchestrator.graph._local_commit")
def test_run_loop_retry_then_pass(
    mock_commit, mock_diff, mock_verify, mock_sysdebug, mock_reflect, mock_reviewer, mock_executor, mock_planner,
    store: FileStore, tmp_path: Path,
):
    from devboard.agents.base import AgentResult
    from devboard.agents.reviewer import ReviewVerdict

    mock_planner.return_value = AgentResult(PLAN_TEXT, [], _mock_result(PLAN_TEXT))
    mock_executor.return_value = AgentResult(EXEC_TEXT, [], _mock_result(EXEC_TEXT))
    mock_reviewer.side_effect = [
        (ReviewVerdict.retry, AgentResult(REVIEW_RETRY, [], _mock_result(REVIEW_RETRY))),
        (ReviewVerdict.pass_, AgentResult(REVIEW_PASS, [], _mock_result(REVIEW_PASS))),
    ]
    reflect_json = {"root_cause": "x", "next_strategy": "y", "learning": "", "risk": "LOW", "risk_reason": ""}
    mock_reflect.return_value = (reflect_json, AgentResult(REFLECT_TEXT, [], _mock_result(REFLECT_TEXT)))
    mock_sysdebug.return_value = (reflect_json, AgentResult(REFLECT_TEXT, [], _mock_result(REFLECT_TEXT)))
    # verify_node returns a report with full_suite_passed=True so it never blocks the loop
    from devboard.orchestrator.verify import VerificationReport, EvidenceRecord
    rep = VerificationReport(full_suite_passed=True, full_suite_cmd="pytest", full_suite_exit=0, full_suite_tail="")
    mock_verify.return_value = rep

    goal = Goal(title="Hello", description="Add hello.py")
    store.save_goal(goal)

    plan = _make_plan(goal.id)
    result = run_loop(
        goal_id=goal.id,
        task_id="t_002",
        goal_description=goal.description,
        locked_plan=plan,
        project_root=tmp_path,
        store=store,
        client=MagicMock(),
    )

    assert result.converged
    assert result.iteration == 2
    assert mock_planner.call_count == 2
    # Either reflect (legacy) or systematic_debug (Phase G default) was called
    assert mock_reflect.call_count + mock_sysdebug.call_count == 1


@patch("devboard.orchestrator.graph.run_planner")
@patch("devboard.orchestrator.graph.run_executor")
@patch("devboard.orchestrator.graph.run_reviewer")
@patch("devboard.orchestrator.graph.run_reflect")
@patch("devboard.orchestrator.graph.run_systematic_debug")
@patch("devboard.orchestrator.graph.verify_checklist")
@patch("devboard.orchestrator.graph._get_diff", return_value="")
@patch("devboard.orchestrator.graph._local_commit")
def test_run_loop_max_iterations_blocks(
    mock_commit, mock_diff, mock_verify, mock_sysdebug, mock_reflect, mock_reviewer, mock_executor, mock_planner,
    store: FileStore, tmp_path: Path,
):
    from devboard.agents.base import AgentResult
    from devboard.agents.reviewer import ReviewVerdict

    mock_planner.return_value = AgentResult(PLAN_TEXT, [], _mock_result(PLAN_TEXT))
    mock_executor.return_value = AgentResult(EXEC_TEXT, [], _mock_result(EXEC_TEXT))
    mock_reviewer.return_value = (ReviewVerdict.retry, AgentResult(REVIEW_RETRY, [], _mock_result(REVIEW_RETRY)))
    reflect_json = {"root_cause": "x", "next_strategy": "y", "learning": "", "risk": "HIGH", "risk_reason": "stuck", "escalate": False}
    mock_reflect.return_value = (reflect_json, AgentResult(REFLECT_TEXT, [], _mock_result(REFLECT_TEXT)))
    mock_sysdebug.return_value = (reflect_json, AgentResult(REFLECT_TEXT, [], _mock_result(REFLECT_TEXT)))
    from devboard.orchestrator.verify import VerificationReport
    mock_verify.return_value = VerificationReport(full_suite_passed=True, full_suite_exit=0)

    goal = Goal(title="Hello", description="Add hello.py")
    store.save_goal(goal)

    # Plan allows only 2 iterations
    from devboard.gauntlet.lock import build_locked_plan
    plan = build_locked_plan(goal.id, {
        "problem": "p", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "token_ceiling": 100_000, "max_iterations": 2,
    })

    result = run_loop(
        goal_id=goal.id,
        task_id="t_003",
        goal_description=goal.description,
        locked_plan=plan,
        project_root=tmp_path,
        store=store,
        client=MagicMock(),
    )

    assert not result.converged
    assert result.blocked
    assert "Max iterations" in result.block_reason


@patch("devboard.orchestrator.graph.run_planner")
@patch("devboard.orchestrator.graph.run_executor")
@patch("devboard.orchestrator.graph.run_reviewer")
@patch("devboard.orchestrator.graph._get_diff", return_value="")
@patch("devboard.orchestrator.graph._local_commit")
def test_run_loop_replan_blocks(
    mock_commit, mock_diff, mock_reviewer, mock_executor, mock_planner,
    store: FileStore, tmp_path: Path,
):
    from devboard.agents.base import AgentResult
    from devboard.agents.reviewer import ReviewVerdict

    mock_planner.return_value = AgentResult(PLAN_TEXT, [], _mock_result(PLAN_TEXT))
    mock_executor.return_value = AgentResult(EXEC_TEXT, [], _mock_result(EXEC_TEXT))
    mock_reviewer.return_value = (ReviewVerdict.replan, AgentResult("Verdict: REPLAN", [], _mock_result("Verdict: REPLAN")))

    goal = Goal(title="Hello", description="Add hello.py")
    store.save_goal(goal)

    plan = _make_plan(goal.id)
    result = run_loop(
        goal_id=goal.id,
        task_id="t_004",
        goal_description=goal.description,
        locked_plan=plan,
        project_root=tmp_path,
        store=store,
        client=MagicMock(),
    )

    assert not result.converged
    assert result.blocked
    assert "REPLAN" in result.block_reason


def test_checkpointer_persists_across_run(store: FileStore, tmp_path: Path):
    """Verify checkpoints are written to disk during the loop."""
    with (
        patch("devboard.orchestrator.graph.run_planner") as mp,
        patch("devboard.orchestrator.graph.run_executor") as me,
        patch("devboard.orchestrator.graph.run_reviewer") as mr,
        patch("devboard.orchestrator.graph._get_diff", return_value=""),
        patch("devboard.orchestrator.graph._local_commit"),
    ):
        from devboard.agents.base import AgentResult
        from devboard.agents.reviewer import ReviewVerdict

        mp.return_value = AgentResult(PLAN_TEXT, [], _mock_result(PLAN_TEXT))
        me.return_value = AgentResult(EXEC_TEXT, [], _mock_result(EXEC_TEXT))
        mr.return_value = (ReviewVerdict.pass_, AgentResult(REVIEW_PASS, [], _mock_result(REVIEW_PASS)))

        goal = Goal(title="Hello", description="Add hello.py")
        store.save_goal(goal)
        plan = _make_plan(goal.id)

        run_loop(
            goal_id=goal.id,
            task_id="t_005",
            goal_description=goal.description,
            locked_plan=plan,
            project_root=tmp_path,
            store=store,
            run_id="test_run_001",
            client=MagicMock(),
        )

    run_file = tmp_path / ".devboard" / "runs" / "test_run_001.jsonl"
    assert run_file.exists()
    cp = Checkpointer(run_file)
    entries = cp.load_all()
    events = [e["event"] for e in entries]
    assert "run_start" in events
    assert "plan_complete" in events
    assert "execute_complete" in events
    assert "review_complete" in events
    assert "converged" in events
