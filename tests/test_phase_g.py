from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentboard.agents.iron_law import IronLawVerdict, _is_test_path, check_iron_law
from agentboard.agents.systematic_debug import _parse_rca
from agentboard.agents.tdd import parse_green_status, parse_red_status, parse_refactor_status
from agentboard.gauntlet.steps.brainstorm import needs_brainstorm, parse_questions
from agentboard.tools.base import ToolCall
from agentboard.config import AgentBoardConfig, TDDConfig
from agentboard.gauntlet.lock import build_locked_plan
from agentboard.llm.client import CompletionResult
from agentboard.models import AtomicStep, BoardState, Goal, LockedPlan
from agentboard.orchestrator.verify import (
    EvidenceRecord, VerificationReport, _keywords_from_item,
    _tail, verify_checklist,
)
from agentboard.storage.file_store import FileStore


# ── G1-a: AtomicStep + LockedPlan schema ──────────────────────────────────────

def test_atomic_step_roundtrip():
    step = AtomicStep(
        id="s_001", behavior="add(1,2) returns 3",
        test_file="tests/test_calc.py", test_name="test_add",
        impl_file="calculator.py",
    )
    dumped = step.model_dump()
    loaded = AtomicStep.model_validate(dumped)
    assert loaded.id == "s_001"
    assert loaded.behavior == "add(1,2) returns 3"
    assert not loaded.completed


def test_locked_plan_next_step():
    plan = LockedPlan(goal_id="g", atomic_steps=[
        AtomicStep(id="s_1", behavior="a", test_file="t", test_name="n"),
        AtomicStep(id="s_2", behavior="b", test_file="t", test_name="n"),
    ])
    assert plan.next_step().id == "s_1"
    plan.mark_step_completed("s_1")
    assert plan.next_step().id == "s_2"
    plan.mark_step_completed("s_2")
    assert plan.next_step() is None


def test_build_locked_plan_with_atomic_steps():
    plan = build_locked_plan("g_001", {
        "problem": "p", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "atomic_steps": [
            {"id": "s_1", "behavior": "add works", "test_file": "t.py",
             "test_name": "test_add", "impl_file": "calc.py",
             "expected_fail_reason": "NameError"},
        ],
        "token_ceiling": 100_000, "max_iterations": 3,
    })
    assert len(plan.atomic_steps) == 1
    assert plan.atomic_steps[0].id == "s_1"
    assert plan.atomic_steps[0].expected_fail_reason == "NameError"


def test_build_locked_plan_generates_missing_ids():
    plan = build_locked_plan("g_001", {
        "problem": "p", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": [], "out_of_scope_guard": [],
        "atomic_steps": [
            {"behavior": "x", "test_file": "t", "test_name": "n"},
            {"behavior": "y", "test_file": "t", "test_name": "n2"},
        ],
    })
    assert plan.atomic_steps[0].id == "s_001"
    assert plan.atomic_steps[1].id == "s_002"


# ── G6: Config toggles ────────────────────────────────────────────────────────

def test_tdd_config_defaults():
    cfg = AgentBoardConfig()
    assert cfg.tdd.enabled is True
    assert cfg.tdd.strict is False
    assert cfg.tdd.verify_with_evidence is True
    assert cfg.tdd.systematic_debug is True


def test_tdd_config_can_disable():
    cfg = AgentBoardConfig(tdd=TDDConfig(enabled=False, systematic_debug=False))
    assert cfg.tdd.enabled is False
    assert cfg.tdd.systematic_debug is False


# ── G1-b: TDD status parsers ──────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("## RED Phase\nStatus: RED_CONFIRMED", "RED_CONFIRMED"),
    ("Status: RED_FAILED_TO_FAIL — test passed immediately", "RED_FAILED_TO_FAIL"),
    ("Status: BLOCKED", "BLOCKED"),
    ("hmm", "UNCLEAR"),
])
def test_parse_red_status(text, expected):
    assert parse_red_status(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Status: GREEN_CONFIRMED — all tests pass", "GREEN_CONFIRMED"),
    ("Status: REGRESSED — 2 tests now fail", "REGRESSED"),
    ("Status: GREEN_FAILED", "GREEN_FAILED"),
    ("unknown", "UNCLEAR"),
])
def test_parse_green_status(text, expected):
    assert parse_green_status(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("## REFACTOR Phase\nStatus: REFACTORED", "REFACTORED"),
    ("Status: SKIPPED — code already clean", "SKIPPED"),
    ("Status: REGRESSED — reverting", "REGRESSED"),
])
def test_parse_refactor_status(text, expected):
    assert parse_refactor_status(text) == expected


# ── G3: Verification (deterministic) ──────────────────────────────────────────

def test_keywords_from_item():
    kws = _keywords_from_item("add() and sub() functions work correctly")
    assert "add" in kws
    assert "sub" in kws
    assert "functions" in kws


def test_tail_preserves_last_lines():
    text = "\n".join(f"line {i}" for i in range(50))
    result = _tail(text, 5)
    lines = result.splitlines()
    assert len(lines) == 5
    assert lines[-1] == "line 49"


def test_verification_report_summary():
    rep = VerificationReport(
        full_suite_passed=True, full_suite_cmd="pytest", full_suite_exit=0,
        evidence=[
            EvidenceRecord(item="add works", command="pytest", exit_code=0,
                           stdout_tail="", stderr_tail="", passed=True, matched_item=True),
            EvidenceRecord(item="sub works", command="pytest", exit_code=0,
                           stdout_tail="", stderr_tail="", passed=True, matched_item=False),
        ],
    )
    summary = rep.summary()
    assert "Full suite: exit=0" in summary
    assert "add works" in summary
    assert "[✓] add works" in summary
    assert "[✗] sub works" in summary  # matched_item=False so marked as failed


def test_verification_all_items_evidence_property():
    rep_pass = VerificationReport(evidence=[
        EvidenceRecord(item="x", command="", exit_code=0, stdout_tail="", stderr_tail="",
                       passed=True, matched_item=True),
    ])
    assert rep_pass.all_items_have_evidence

    rep_fail = VerificationReport(evidence=[
        EvidenceRecord(item="x", command="", exit_code=0, stdout_tail="", stderr_tail="",
                       passed=True, matched_item=False),  # not matched
    ])
    assert not rep_fail.all_items_have_evidence


def test_verify_checklist_handles_missing_pytest(tmp_path: Path):
    # Passing a nonexistent binary — should not crash, returns failing report
    report = verify_checklist(
        checklist=["add works"],
        project_root=tmp_path,
        pytest_bin="/nonexistent/pytest",
        timeout=5,
    )
    assert not report.full_suite_passed
    assert len(report.evidence) == 1


# ── G4: Systematic debug parser ───────────────────────────────────────────────

def test_parse_rca_full_json():
    text = json.dumps({
        "phase_1_investigate": {"error_summary": "NameError"},
        "phase_2_pattern": {"key_differences": []},
        "phase_3_hypothesis": {"hypothesis": "X causes Y"},
        "phase_4_fix": {
            "regression_test_to_add": "test_x_not_none",
            "risk": "HIGH",
            "consecutive_failures": 3,
            "escalate_if_3_plus": True,
        },
        "root_cause": "missing null check",
        "next_strategy": "add None guard in parse()",
        "learning": "always validate inputs",
    })
    parsed = _parse_rca(text)
    assert parsed["root_cause"] == "missing null check"
    assert parsed["risk"] == "HIGH"
    assert parsed["escalate"] is True
    assert "phases" in parsed


def test_parse_rca_fenced():
    inner = json.dumps({
        "root_cause": "x",
        "next_strategy": "y",
        "phase_4_fix": {"risk": "LOW"},
    })
    text = f"```json\n{inner}\n```\n"
    parsed = _parse_rca(text)
    assert parsed["root_cause"] == "x"
    assert parsed["risk"] == "LOW"


def test_parse_rca_fallback_on_invalid():
    parsed = _parse_rca("not json at all")
    assert parsed["risk"] == "MEDIUM"
    assert parsed["escalate"] is False


def test_parse_rca_no_escalate_under_3():
    text = json.dumps({
        "phase_4_fix": {
            "consecutive_failures": 2,
            "escalate_if_3_plus": True,
        },
        "root_cause": "x", "next_strategy": "y",
    })
    parsed = _parse_rca(text)
    assert parsed["escalate"] is False


# ── G1-b integration: TDD path executes red → green → verify ──────────────────

def _r(text):
    r = CompletionResult(text=text, thinking="", input_tokens=10, output_tokens=5,
                         model="sonnet", cached_tokens=0)
    r._raw_content = []
    return r


@patch("agentboard.orchestrator.graph.run_tdd_red")
@patch("agentboard.orchestrator.graph.run_tdd_green")
@patch("agentboard.orchestrator.graph.run_tdd_refactor")
@patch("agentboard.orchestrator.graph.verify_checklist")
@patch("agentboard.orchestrator.graph.run_planner")
@patch("agentboard.orchestrator.graph.run_reviewer")
@patch("agentboard.orchestrator.graph._get_diff", return_value="")
@patch("agentboard.orchestrator.graph._local_commit")
def test_tdd_path_executes_red_green_verify(
    mock_commit, mock_diff, mock_reviewer, mock_planner,
    mock_verify, mock_refactor, mock_green, mock_red,
    tmp_path: Path,
):
    from agentboard.agents.base import AgentResult
    from agentboard.agents.reviewer import ReviewVerdict
    from agentboard.orchestrator.runner import run_loop

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()

    # Plan has 1 atomic step so TDD path activates
    plan = build_locked_plan("g_001", {
        "problem": "add", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "single calc.py", "known_failure_modes": [],
        "goal_checklist": ["add works"], "out_of_scope_guard": [],
        "atomic_steps": [
            {"id": "s_001", "behavior": "add(1,2)==3",
             "test_file": "tests/test_calc.py", "test_name": "test_add",
             "impl_file": "calc.py", "expected_fail_reason": "NameError"},
        ],
        "token_ceiling": 100_000, "max_iterations": 3,
    })

    mock_planner.return_value = AgentResult("plan", [], _r("plan"))
    mock_red.return_value = AgentResult("RED_CONFIRMED — test fails as expected", [], _r("red"))
    mock_green.return_value = AgentResult("GREEN_CONFIRMED — test passes", [], _r("green"))
    mock_refactor.return_value = AgentResult("SKIPPED — clean", [], _r("refactor"))
    mock_verify.return_value = VerificationReport(full_suite_passed=True, full_suite_exit=0)
    mock_reviewer.return_value = (ReviewVerdict.pass_, AgentResult("Verdict: PASS", [], _r("PASS")))

    goal = Goal(title="Test", description="test")
    store.save_goal(goal)

    result = run_loop(
        goal_id=goal.id, task_id="t_tdd", goal_description="test",
        locked_plan=plan, project_root=tmp_path, store=store,
        client=MagicMock(), enable_redteam=False,
    )

    assert result.converged
    assert mock_red.call_count == 1
    assert mock_green.call_count == 1
    assert mock_verify.call_count >= 1


@patch("agentboard.orchestrator.graph.run_planner")
@patch("agentboard.orchestrator.graph.run_executor")
@patch("agentboard.orchestrator.graph.run_reviewer")
@patch("agentboard.orchestrator.graph.run_systematic_debug")
@patch("agentboard.orchestrator.graph.verify_checklist")
@patch("agentboard.orchestrator.graph._get_diff", return_value="")
@patch("agentboard.orchestrator.graph._local_commit")
def test_rca_escalates_after_3_consecutive_failures(
    mock_commit, mock_diff, mock_verify, mock_sysdebug, mock_reviewer, mock_executor, mock_planner,
    tmp_path: Path,
):
    from agentboard.agents.base import AgentResult
    from agentboard.agents.reviewer import ReviewVerdict
    from agentboard.orchestrator.runner import run_loop

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()

    # No atomic_steps → legacy path used
    plan = build_locked_plan("g_001", {
        "problem": "p", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "token_ceiling": 100_000, "max_iterations": 5,
    })

    mock_planner.return_value = AgentResult("plan", [], _r("plan"))
    mock_executor.return_value = AgentResult("exec", [], _r("exec"))
    mock_reviewer.return_value = (ReviewVerdict.retry, AgentResult("Verdict: RETRY", [], _r("RETRY")))
    mock_verify.return_value = VerificationReport(full_suite_passed=False, full_suite_exit=1)

    # First 2 RCA calls: no escalate. 3rd: escalate.
    mock_sysdebug.side_effect = [
        ({"root_cause": "x", "next_strategy": "y", "learning": "", "risk": "MEDIUM",
          "risk_reason": "", "escalate": False, "phases": {}}, AgentResult("r", [], _r("r"))),
        ({"root_cause": "x", "next_strategy": "y", "learning": "", "risk": "HIGH",
          "risk_reason": "", "escalate": False, "phases": {}}, AgentResult("r", [], _r("r"))),
        ({"root_cause": "x", "next_strategy": "y", "learning": "", "risk": "HIGH",
          "risk_reason": "", "escalate": True, "phases": {}}, AgentResult("r", [], _r("r"))),
    ]

    goal = Goal(title="Stuck", description="stuck test")
    store.save_goal(goal)

    result = run_loop(
        goal_id=goal.id, task_id="t_rca", goal_description="test",
        locked_plan=plan, project_root=tmp_path, store=store,
        client=MagicMock(), enable_redteam=False,
    )

    assert not result.converged
    assert result.blocked
    # Either escalation via "Systematic debug escalates" or max_iterations
    assert ("escalates" in result.block_reason or "consecutive" in result.block_reason
            or "Max iterations" in result.block_reason)


# ── G5: Brainstorm gate ──────────────────────────────────────────────────────

def test_needs_brainstorm_short_goal():
    assert needs_brainstorm("build stuff")


def test_needs_brainstorm_vague_words():
    assert needs_brainstorm("build something like a calculator but maybe more")
    assert needs_brainstorm("add some features, kinda like auth etc")


def test_needs_brainstorm_clear_goal_skipped():
    assert not needs_brainstorm(
        "Implement calculator.py with add/sub/mul/div functions and a pytest suite. "
        "div(a, 0) must raise ZeroDivisionError."
    )


def test_parse_questions_clear():
    result = parse_questions("## Brainstorm\nCLEAR — no questions needed.")
    assert result == []


def test_parse_questions_extracts_numbered_list():
    text = """## Brainstorm — 2 questions

1. **Success criteria**: How will we know the calculator is done?
2. **Constraints**: Does this need to run on Python 3.11?"""
    questions = parse_questions(text)
    assert len(questions) == 2
    assert "calculator is done" in questions[0]
    assert "Python 3.11" in questions[1]


# ── G7: Iron Law detector ────────────────────────────────────────────────────

def test_is_test_path():
    assert _is_test_path("tests/test_calc.py")
    assert _is_test_path("src/foo/test_utils.py")
    assert _is_test_path("my_module_test.py")
    assert not _is_test_path("calculator.py")
    assert not _is_test_path("src/utils.py")


def _tc(name: str, inp: dict) -> ToolCall:
    return ToolCall(tool_name=name, tool_input=inp, result="ok", error=False)


def test_iron_law_ok_tests_before_impl():
    calls = [
        _tc("fs_write", {"path": "tests/test_calc.py", "content": "def test_add(): ..."}),
        _tc("shell", {"command": "pytest tests/test_calc.py"}),
        _tc("fs_write", {"path": "calc.py", "content": "def add(a,b): return a+b"}),
    ]
    v = check_iron_law(calls)
    assert not v.violated


def test_iron_law_violated_no_tests():
    calls = [
        _tc("fs_write", {"path": "calc.py", "content": "def add(a,b): return a+b"}),
    ]
    v = check_iron_law(calls)
    assert v.violated
    assert "without any test" in v.reason


def test_iron_law_violated_impl_before_test():
    calls = [
        _tc("fs_write", {"path": "calc.py", "content": "def add(a,b): return a+b"}),
        _tc("fs_write", {"path": "tests/test_calc.py", "content": "def test_add(): ..."}),
    ]
    v = check_iron_law(calls)
    assert v.violated
    assert "AFTER production code" in v.reason


def test_iron_law_only_tests_ok():
    calls = [
        _tc("fs_write", {"path": "tests/test_calc.py", "content": "def test_add(): ..."}),
    ]
    v = check_iron_law(calls)
    assert not v.violated
    assert v.test_writes == ["tests/test_calc.py"]


def test_iron_law_ignores_non_writes():
    calls = [
        _tc("fs_read", {"path": "calc.py"}),
        _tc("shell", {"command": "ls"}),
        _tc("fs_list", {"path": "."}),
    ]
    v = check_iron_law(calls)
    assert not v.violated
    assert v.impl_writes == []
    assert v.test_writes == []


@patch("agentboard.orchestrator.graph.run_planner")
@patch("agentboard.orchestrator.graph.run_executor")
@patch("agentboard.orchestrator.graph.run_reviewer")
@patch("agentboard.orchestrator.graph.verify_checklist")
@patch("agentboard.orchestrator.graph._get_diff", return_value="")
@patch("agentboard.orchestrator.graph._local_commit")
def test_iron_law_strict_blocks_loop(
    mock_commit, mock_diff, mock_verify, mock_reviewer, mock_executor, mock_planner,
    tmp_path: Path,
):
    """In strict mode, Iron Law violation in legacy executor path should block."""
    from agentboard.agents.base import AgentResult
    from agentboard.agents.reviewer import ReviewVerdict
    from agentboard.config import AgentBoardConfig, TDDConfig
    from agentboard.orchestrator.runner import run_loop

    store = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()

    plan = build_locked_plan("g_001", {
        "problem": "p", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "token_ceiling": 100_000, "max_iterations": 3,
        # no atomic_steps → legacy path
    })

    # Executor commits production code without a test — Iron Law violation
    iron_violating_calls = [
        ToolCall(tool_name="fs_write", tool_input={"path": "calc.py", "content": "x"}, result="ok"),
    ]
    mock_planner.return_value = AgentResult("plan", [], _r("plan"))
    mock_executor.return_value = AgentResult("exec", iron_violating_calls, _r("exec"))
    mock_reviewer.return_value = (ReviewVerdict.pass_, AgentResult("PASS", [], _r("PASS")))
    mock_verify.return_value = VerificationReport(full_suite_passed=True, full_suite_exit=0)

    goal = Goal(title="Strict", description="test")
    store.save_goal(goal)

    cfg = AgentBoardConfig(tdd=TDDConfig(enabled=False, strict=True, verify_with_evidence=False))

    result = run_loop(
        goal_id=goal.id, task_id="t_iron", goal_description="test",
        locked_plan=plan, project_root=tmp_path, store=store,
        config=cfg, client=MagicMock(), enable_redteam=False,
    )

    assert result.blocked
    assert "Iron Law" in result.block_reason
