from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentboard.agents.redteam import _parse_survived
from agentboard.agents.router import route, budget_tier, _DOWNGRADE_AT, _EMERGENCY_AT
from agentboard.config import LLMConfig
from agentboard.llm.client import BudgetTracker
from agentboard.memory.retriever import load_relevant_learnings, _tokenize
from agentboard.models import Goal, BoardState, LockedPlan
from agentboard.orchestrator.interrupt import HintQueue, get_hint_queue, reset_hint_queue
from agentboard.replay.replay import branch_run, find_state_at_iteration, list_runs
from agentboard.orchestrator.checkpointer import Checkpointer
from agentboard.storage.file_store import FileStore
from agentboard.tools.fs import make_fs_tools, _check_scope
from agentboard.tools.base import ToolRegistry


# ── Red-team ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Verdict: SURVIVED — no critical issues found.", True),
    ("**SURVIVED** — implementation is solid.", True),
    ("Verdict: BROKEN — found CRITICAL edge case.", False),
    ("**BROKEN** — null input causes crash.", False),
    ("CRITICAL issue: div by zero not handled. BROKEN.", False),
    ("No major issues found, implementation looks good.", True),  # heuristic default
])
def test_parse_survived(text, expected):
    assert _parse_survived(text) == expected


# ── Cost-aware router ─────────────────────────────────────────────────────────

def _budget(used: int, ceiling: int) -> BudgetTracker:
    b = BudgetTracker(goal_id="g", token_ceiling=ceiling)
    b.tokens_used = used
    return b


def test_route_no_budget_returns_base():
    cfg = LLMConfig()
    model = route("planner", cfg)
    assert model == cfg.planner_model


def test_route_normal_budget():
    cfg = LLMConfig()
    b = _budget(10_000, 100_000)  # 10% used — normal
    assert route("planner", cfg, b) == cfg.planner_model


def test_route_downgrade_at_70pct():
    cfg = LLMConfig()
    b = _budget(75_000, 100_000)  # 75% used — reduced tier
    model = route("planner", cfg, b)
    assert "opus" not in model  # downgraded from opus


def test_route_emergency_at_90pct():
    cfg = LLMConfig()
    b = _budget(92_000, 100_000)  # 92% used — emergency
    for role in ["planner", "reviewer", "executor"]:
        assert route(role, cfg, b) == cfg.haiku_model


def test_budget_tier_labels():
    cfg = LLMConfig()
    assert budget_tier(_budget(0, 100_000)) == "normal"
    assert budget_tier(_budget(75_000, 100_000)) == "reduced"
    assert budget_tier(_budget(92_000, 100_000)) == "emergency"
    assert budget_tier(_budget(0, 0)) == "unlimited"


# ── Scoped FS ─────────────────────────────────────────────────────────────────

def test_fs_forbids_blocks_write(tmp_path: Path):
    reg = ToolRegistry()
    make_fs_tools(tmp_path, reg, forbids=["src/payments/"])
    result = reg.execute("fs_write", {"path": "src/payments/ledger.py", "content": "x"})
    assert result.startswith("ERROR:")
    assert "out_of_scope_guard" in result or "guard" in result.lower()


def test_fs_forbids_blocks_read(tmp_path: Path):
    (tmp_path / "src" / "payments").mkdir(parents=True)
    (tmp_path / "src" / "payments" / "secret.py").write_text("SECRET")
    reg = ToolRegistry()
    make_fs_tools(tmp_path, reg, forbids=["src/payments/"])
    result = reg.execute("fs_read", {"path": "src/payments/secret.py"})
    assert result.startswith("ERROR:")


def test_fs_touches_restricts_writes(tmp_path: Path):
    reg = ToolRegistry()
    make_fs_tools(tmp_path, reg, touches=["src/calc/"], forbids=[])
    # Write inside touches — OK
    result = reg.execute("fs_write", {"path": "src/calc/main.py", "content": "x"})
    assert "Written" in result

    # Write outside touches — blocked
    result2 = reg.execute("fs_write", {"path": "src/auth/login.py", "content": "y"})
    assert result2.startswith("ERROR:")


def test_fs_touches_does_not_restrict_reads(tmp_path: Path):
    (tmp_path / "other.txt").write_text("hello")
    reg = ToolRegistry()
    make_fs_tools(tmp_path, reg, touches=["src/calc/"], forbids=[])
    # Reads are unrestricted even outside touches
    result = reg.execute("fs_read", {"path": "other.txt"})
    assert result == "hello"


# ── HITL HintQueue ────────────────────────────────────────────────────────────

def test_hint_queue_inject_drain():
    hq = reset_hint_queue()
    hq.inject("fix the edge case")
    hq.inject("also add type hints")
    hints = hq.drain()
    assert len(hints) == 2
    assert hints[0].text == "fix the edge case"
    assert hints[1].text == "also add type hints"
    # Drain is destructive
    assert hq.drain() == []


def test_hint_queue_pause_resume():
    hq = reset_hint_queue()
    assert not hq.is_paused
    hq.pause()
    assert hq.is_paused
    hq.resume()
    assert not hq.is_paused


def test_hint_queue_singleton():
    hq1 = get_hint_queue()
    hq2 = get_hint_queue()
    assert hq1 is hq2


# ── Learnings Retriever ───────────────────────────────────────────────────────

def test_tokenize():
    tokens = _tokenize("Build a calculator with add/sub/mul/div")
    assert "calculator" in tokens
    assert "add" in tokens
    # length >= 2 filter (Phase H upgrade) — single chars excluded
    assert "a" not in tokens


def test_load_relevant_learnings_empty(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    result = load_relevant_learnings(store, "build something")
    assert result == ""


def test_load_relevant_learnings_scores(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    (tmp_path / ".devboard" / "learnings").mkdir()
    # Relevant learning
    (tmp_path / ".devboard" / "learnings" / "calc_tip.md").write_text(
        "When building calculator functions, always handle ZeroDivisionError explicitly."
    )
    # Irrelevant learning
    (tmp_path / ".devboard" / "learnings" / "auth_tip.md").write_text(
        "JWT tokens expire after 1 hour. Always refresh before expiry."
    )
    result = load_relevant_learnings(store, "build calculator with division")
    assert "calc_tip" in result or "ZeroDivision" in result


def test_load_relevant_learnings_max(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    (tmp_path / ".devboard" / "learnings").mkdir()
    for i in range(10):
        (tmp_path / ".devboard" / "learnings" / f"tip_{i}.md").write_text(f"learning {i} about stuff")
    result = load_relevant_learnings(store, "stuff", max_learnings=3)
    # Should return at most 3 learnings
    assert result.count("###") <= 3


# ── Time-travel Replay ────────────────────────────────────────────────────────

def test_find_state_at_iteration(tmp_path: Path):
    cp = Checkpointer(tmp_path / "run.jsonl")
    cp.save("iteration_complete", {"iteration": 2, "converged": False})
    cp.save("iteration_complete", {"iteration": 3, "converged": True})

    state = find_state_at_iteration(cp, 2)
    assert state is not None
    assert state["iteration"] in (2, 3)


def test_branch_run_not_found(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    from agentboard.gauntlet.lock import build_locked_plan
    plan = build_locked_plan("g_001", {
        "problem": "x", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "x", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "token_ceiling": 100_000, "max_iterations": 3,
    })
    result = branch_run("nonexistent_run", 1, store, plan)
    assert result is None


def test_branch_run_success(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    (tmp_path / ".devboard" / "runs").mkdir(parents=True)

    # Create a fake run checkpoint
    cp = Checkpointer(tmp_path / ".devboard" / "runs" / "run_abc.jsonl")
    cp.save("iteration_complete", {
        "iteration": 2,
        "goal_id": "g_001",
        "task_id": "t_001",
        "goal_description": "Build something",
        "converged": False,
        "reflect_json": {"next_strategy": "try harder"},
        "history": [{"n": 1}],
    })

    from agentboard.gauntlet.lock import build_locked_plan
    plan = build_locked_plan("g_001", {
        "problem": "x", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "x", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "token_ceiling": 100_000, "max_iterations": 5,
    })

    result = branch_run("run_abc", 2, store, plan, variant_note="testing replay")
    assert result is not None
    new_run_id, initial_state = result
    assert new_run_id.startswith("replay_")
    assert initial_state["iteration"] == 3  # from_iteration + 1
    assert not initial_state["converged"]
    assert not initial_state["blocked"]


def test_list_runs(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    (tmp_path / ".devboard" / "runs").mkdir(parents=True)

    cp1 = Checkpointer(tmp_path / ".devboard" / "runs" / "run_001.jsonl")
    cp1.save("converged", {"iteration": 2})
    cp2 = Checkpointer(tmp_path / ".devboard" / "runs" / "run_002.jsonl")
    cp2.save("blocked", {"iteration": 3})

    runs = list_runs(store)
    assert len(runs) == 2
    run_ids = [r["run_id"] for r in runs]
    assert "run_001" in run_ids
    assert "run_002" in run_ids
    converged = next(r for r in runs if r["run_id"] == "run_001")
    assert converged["converged"]


# ── Graph integration: red-team + hints ──────────────────────────────────────

@patch("agentboard.orchestrator.graph.run_planner")
@patch("agentboard.orchestrator.graph.run_executor")
@patch("agentboard.orchestrator.graph.run_reviewer")
@patch("agentboard.orchestrator.graph.run_redteam")
@patch("agentboard.orchestrator.graph.run_reflect")
@patch("agentboard.orchestrator.graph.run_systematic_debug")
@patch("agentboard.orchestrator.graph.verify_checklist")
@patch("agentboard.orchestrator.graph._get_diff", return_value="")
@patch("agentboard.orchestrator.graph._local_commit")
def test_graph_redteam_broken_becomes_retry(
    mock_commit, mock_diff, mock_verify, mock_sysdebug, mock_reflect, mock_redteam, mock_reviewer, mock_executor, mock_planner,
    tmp_path: Path,
):
    from agentboard.agents.base import AgentResult
    from agentboard.agents.reviewer import ReviewVerdict
    from agentboard.llm.client import CompletionResult
    from agentboard.models import BoardState, Goal
    from agentboard.orchestrator.runner import run_loop

    def _r(text):
        r = CompletionResult(text=text, thinking="", input_tokens=10, output_tokens=5, model="sonnet", cached_tokens=0)
        r._raw_content = []
        return r

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()

    # Iter 1: reviewer PASS → redteam BROKEN → back to reflect/retry
    # Iter 2: reviewer PASS → redteam SURVIVED → commit
    reflect_json = {"root_cause": "missing edge case", "next_strategy": "add test", "learning": "", "risk": "LOW", "risk_reason": "", "escalate": False}
    mock_planner.return_value = AgentResult("plan", [], _r("plan"))
    mock_executor.return_value = AgentResult("exec", [], _r("exec"))
    mock_reviewer.side_effect = [
        (ReviewVerdict.pass_, AgentResult("Verdict: PASS", [], _r("PASS"))),
        (ReviewVerdict.pass_, AgentResult("Verdict: PASS", [], _r("PASS"))),
    ]
    mock_redteam.side_effect = [
        (False, AgentResult("Verdict: BROKEN — div-by-zero", [], _r("BROKEN"))),
        (True, AgentResult("Verdict: SURVIVED", [], _r("SURVIVED"))),
    ]
    mock_reflect.return_value = (reflect_json, AgentResult("reflect", [], _r("reflect")))
    mock_sysdebug.return_value = (reflect_json, AgentResult("reflect", [], _r("reflect")))
    from agentboard.orchestrator.verify import VerificationReport
    mock_verify.return_value = VerificationReport(full_suite_passed=True, full_suite_exit=0)

    goal = Goal(title="Test", description="test")
    store.save_goal(goal)

    from agentboard.gauntlet.lock import build_locked_plan
    plan = build_locked_plan(goal.id, {
        "problem": "p", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "token_ceiling": 100_000, "max_iterations": 3,
    })

    result = run_loop(
        goal_id=goal.id, task_id="t_redteam", goal_description="test",
        locked_plan=plan, project_root=tmp_path, store=store,
        client=MagicMock(), enable_redteam=True,
    )

    assert result.converged
    assert mock_redteam.call_count == 2
    assert result.iteration == 2


@patch("agentboard.orchestrator.graph.run_planner")
@patch("agentboard.orchestrator.graph.run_executor")
@patch("agentboard.orchestrator.graph.run_reviewer")
@patch("agentboard.orchestrator.graph.verify_checklist")
@patch("agentboard.orchestrator.graph._get_diff", return_value="")
@patch("agentboard.orchestrator.graph._local_commit")
def test_graph_hint_injected_into_plan(
    mock_commit, mock_diff, mock_verify, mock_reviewer, mock_executor, mock_planner,
    tmp_path: Path,
):
    from agentboard.agents.base import AgentResult
    from agentboard.agents.reviewer import ReviewVerdict
    from agentboard.llm.client import CompletionResult
    from agentboard.models import Goal
    from agentboard.orchestrator.interrupt import reset_hint_queue
    from agentboard.orchestrator.runner import run_loop

    def _r(text):
        r = CompletionResult(text=text, thinking="", input_tokens=10, output_tokens=5, model="sonnet", cached_tokens=0)
        r._raw_content = []
        return r

    hq = reset_hint_queue()
    hq.inject("Focus on the edge case where x=0")

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()

    captured_calls = []

    def capture_planner(*args, **kwargs):
        captured_calls.append(kwargs.get("previous_strategy", ""))
        return AgentResult("plan", [], _r("plan"))

    mock_planner.side_effect = capture_planner
    mock_executor.return_value = AgentResult("exec", [], _r("exec"))
    mock_reviewer.return_value = (ReviewVerdict.pass_, AgentResult("Verdict: PASS", [], _r("PASS")))
    from agentboard.orchestrator.verify import VerificationReport
    mock_verify.return_value = VerificationReport(full_suite_passed=True, full_suite_exit=0)

    goal = Goal(title="Test", description="test")
    store.save_goal(goal)

    from agentboard.gauntlet.lock import build_locked_plan
    plan = build_locked_plan(goal.id, {
        "problem": "p", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "token_ceiling": 100_000, "max_iterations": 3,
    })

    run_loop(
        goal_id=goal.id, task_id="t_hint", goal_description="test",
        locked_plan=plan, project_root=tmp_path, store=store,
        client=MagicMock(), hint_queue=hq, enable_redteam=False,
    )

    # First planner call should contain the hint in previous_strategy
    assert any("edge case" in str(c) for c in captured_calls)
