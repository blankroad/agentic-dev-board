from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devboard.gauntlet.lock import build_locked_plan, parse_decide_output
from devboard.gauntlet.pipeline import GauntletResult, run_gauntlet
from devboard.llm.client import CompletionResult
from devboard.models import Goal, BoardState
from devboard.storage.file_store import FileStore


# ── Helpers ────────────────────────────────────────────────────────────────

def _mock_result(text: str, model: str = "claude-sonnet-4-6") -> CompletionResult:
    return CompletionResult(
        text=text,
        thinking="",
        input_tokens=100,
        output_tokens=50,
        model=model,
        cached_tokens=20,
    )


FRAME_OUTPUT = """## Problem
Developers need a calculator module with arithmetic operations.

## Wedge
Four functions: add, sub, mul, div.

## Non-goals
- GUI
- Scientific operations

## Success Definition
- [ ] add/sub/mul/div implemented
- [ ] pytest suite passes

## Key Assumptions
- Python 3.11+ environment available

## Riskiest Assumption
Division by zero is handled — if not, runtime exceptions will propagate."""

SCOPE_OUTPUT = """## Scope Mode
HOLD

## Rationale
Goal is well-scoped. Four functions with tests is the right MVP.

## Scope Changes
No changes.

## Refined Goal Statement
Implement calculator.py with add/sub/mul/div (div raises ZeroDivisionError) and a passing pytest suite.

## Scope Boundaries
### In scope
- calculator.py with 4 functions
- test_calculator.py
### Out of scope
- CLI interface
- persistence"""

ARCH_OUTPUT = """## Architecture Overview
Single module `calculator.py`. Four pure functions.

## Data Flow
Input: two numbers → function → result or exception

## Critical Files
### Create
- `calculator.py`: arithmetic functions
- `tests/test_calculator.py`: pytest suite

## Edge Cases
- **div(a, 0)**: must raise ZeroDivisionError explicitly

## Test Strategy
### Must test
- div-by-zero case: real exception, not mocked
### Do not mock
- arithmetic operations themselves
### Safe to skip
- type coercion edge cases in MVP

## Critical Path
div() must correctly raise ZeroDivisionError.

## Out-of-scope Guard
- `src/payments/`
- `src/auth/`"""

CHALLENGE_OUTPUT = """## Failure Mode 1: Silent float division — HIGH
**Why it fails**: int/int returns float in Python 3, test may assert wrong type
**Mitigation**: document return type as float in docstring
**Warrants replan?**: NO

## Failure Mode 2: Missing div-by-zero test — CRITICAL
**Why it fails**: without explicit test, edge case gets missed
**Mitigation**: add `test_div_by_zero` asserting ZeroDivisionError
**Warrants replan?**: NO

## Summary
### CRITICAL issues
- Missing div-by-zero test
### HIGH issues
- Float return type surprise"""

DECIDE_OUTPUT = json.dumps({
    "problem": "Need a calculator module with add/sub/mul/div",
    "non_goals": ["GUI", "scientific operations"],
    "scope_decision": "HOLD",
    "architecture": "Single calculator.py with 4 pure functions + pytest suite",
    "known_failure_modes": ["CRITICAL: Missing div-by-zero test", "HIGH: Float return type"],
    "goal_checklist": [
        "calculator.py with add/sub/mul/div",
        "div raises ZeroDivisionError on zero divisor",
        "pytest suite passes",
    ],
    "out_of_scope_guard": ["src/payments/", "src/auth/"],
    "token_ceiling": 150000,
    "max_iterations": 5,
    "borderline_decisions": [],
})


# ── Unit tests: lock.py ────────────────────────────────────────────────────

def test_parse_decide_output_clean_json():
    parsed = parse_decide_output(DECIDE_OUTPUT)
    assert parsed["scope_decision"] == "HOLD"
    assert len(parsed["goal_checklist"]) == 3
    assert parsed["token_ceiling"] == 150000


def test_parse_decide_output_with_fences():
    fenced = f"```json\n{DECIDE_OUTPUT}\n```"
    parsed = parse_decide_output(fenced)
    assert parsed["max_iterations"] == 5


def test_build_locked_plan():
    parsed = parse_decide_output(DECIDE_OUTPUT)
    parsed.pop("borderline_decisions", None)
    plan = build_locked_plan("g_test_001", parsed)

    assert plan.goal_id == "g_test_001"
    assert plan.locked_hash != ""
    assert len(plan.goal_checklist) == 3
    assert plan.max_iterations == 5
    assert plan.token_ceiling == 150000
    assert "src/payments/" in plan.out_of_scope_guard


def test_locked_plan_hash_deterministic():
    parsed = parse_decide_output(DECIDE_OUTPUT)
    parsed.pop("borderline_decisions", None)
    plan1 = build_locked_plan("g_001", dict(parsed))
    plan2 = build_locked_plan("g_001", dict(parsed))
    assert plan1.locked_hash == plan2.locked_hash


def test_max_iterations_clamped():
    data = json.loads(DECIDE_OUTPUT)
    data["max_iterations"] = 50
    data.pop("borderline_decisions", None)
    plan = build_locked_plan("g_001", data)
    assert plan.max_iterations == 10

    data["max_iterations"] = 1
    plan2 = build_locked_plan("g_001", data)
    assert plan2.max_iterations == 2


# ── Integration test: pipeline with mocked LLM ────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    s = FileStore(tmp_path)
    (tmp_path / ".devboard").mkdir()
    return s


@patch("devboard.gauntlet.pipeline.run_frame")
@patch("devboard.gauntlet.pipeline.run_scope")
@patch("devboard.gauntlet.pipeline.run_arch")
@patch("devboard.gauntlet.pipeline.run_challenge")
@patch("devboard.gauntlet.pipeline.run_decide")
def test_run_gauntlet_full_pipeline(
    mock_decide, mock_challenge, mock_arch, mock_scope, mock_frame,
    store: FileStore,
    tmp_path: Path,
) -> None:
    mock_frame.return_value = (FRAME_OUTPUT, _mock_result(FRAME_OUTPUT))
    mock_scope.return_value = (SCOPE_OUTPUT, _mock_result(SCOPE_OUTPUT))
    mock_arch.return_value = (ARCH_OUTPUT, _mock_result(ARCH_OUTPUT))
    mock_challenge.return_value = (CHALLENGE_OUTPUT, _mock_result(CHALLENGE_OUTPUT))

    decide_dict = json.loads(DECIDE_OUTPUT)
    decide_dict.pop("borderline_decisions", None)
    mock_decide.return_value = (decide_dict, _mock_result(DECIDE_OUTPUT))

    goal = Goal(title="Build calculator", description="Add/sub/mul/div with pytest")
    store.save_goal(goal)
    board = BoardState()
    board.goals.append(goal)
    store.save_board(board)

    result = run_gauntlet(
        goal_id=goal.id,
        goal_description=goal.description,
        store=store,
        client=MagicMock(),
    )

    assert isinstance(result, GauntletResult)
    assert result.locked_plan.goal_id == goal.id
    assert result.locked_plan.locked_hash != ""
    assert len(result.locked_plan.goal_checklist) == 3
    assert result.locked_plan.scope_decision == "HOLD"

    # gauntlet step files persisted
    gauntlet_dir = store._goals_dir(goal.id) / "gauntlet"
    assert (gauntlet_dir / "frame.md").exists()
    assert (gauntlet_dir / "scope.md").exists()
    assert (gauntlet_dir / "arch.md").exists()
    assert (gauntlet_dir / "challenge.md").exists()
    assert (gauntlet_dir / "decide.md").exists()

    # locked plan persisted
    plan_path = store._goals_dir(goal.id) / "plan.md"
    assert plan_path.exists()
    content = plan_path.read_text()
    assert "HOLD" in content
    assert "calculator" in content.lower()

    loaded = store.load_locked_plan(goal.id)
    assert loaded is not None
    assert loaded.locked_hash == result.locked_plan.locked_hash


@patch("devboard.gauntlet.pipeline.run_frame")
@patch("devboard.gauntlet.pipeline.run_scope")
@patch("devboard.gauntlet.pipeline.run_arch")
@patch("devboard.gauntlet.pipeline.run_challenge")
@patch("devboard.gauntlet.pipeline.run_decide")
def test_gauntlet_borderline_decisions_surfaced(
    mock_decide, mock_challenge, mock_arch, mock_scope, mock_frame,
    store: FileStore,
) -> None:
    mock_frame.return_value = (FRAME_OUTPUT, _mock_result(FRAME_OUTPUT))
    mock_scope.return_value = (SCOPE_OUTPUT, _mock_result(SCOPE_OUTPUT))
    mock_arch.return_value = (ARCH_OUTPUT, _mock_result(ARCH_OUTPUT))
    mock_challenge.return_value = (CHALLENGE_OUTPUT, _mock_result(CHALLENGE_OUTPUT))

    decide_with_borderline = json.loads(DECIDE_OUTPUT)
    decide_with_borderline["borderline_decisions"] = [
        {
            "question": "Should we add type hints?",
            "option_a": "Yes, full type hints",
            "option_b": "No, keep it simple",
            "recommendation": "A",
        }
    ]
    mock_decide.return_value = (decide_with_borderline, _mock_result(DECIDE_OUTPUT))

    goal = Goal(title="Borderline test", description="test")
    store.save_goal(goal)
    board = BoardState()
    board.goals.append(goal)
    store.save_board(board)

    captured_decisions = []

    def on_borderline(decisions):
        captured_decisions.extend(decisions)
        return {"Should we add type hints?": "A"}

    result = run_gauntlet(
        goal_id=goal.id,
        goal_description=goal.description,
        store=store,
        on_borderline=on_borderline,
        client=MagicMock(),
    )

    assert len(captured_decisions) == 1
    assert captured_decisions[0]["question"] == "Should we add type hints?"
    assert result.borderline_decisions == captured_decisions


@patch("devboard.gauntlet.pipeline.run_frame")
@patch("devboard.gauntlet.pipeline.run_scope")
@patch("devboard.gauntlet.pipeline.run_arch")
@patch("devboard.gauntlet.pipeline.run_challenge")
@patch("devboard.gauntlet.pipeline.run_decide")
def test_gauntlet_idempotent_hash(
    mock_decide, mock_challenge, mock_arch, mock_scope, mock_frame,
    store: FileStore,
) -> None:
    """Running gauntlet twice with same inputs produces same locked hash."""
    for mock, text in [
        (mock_frame, FRAME_OUTPUT),
        (mock_scope, SCOPE_OUTPUT),
        (mock_arch, ARCH_OUTPUT),
        (mock_challenge, CHALLENGE_OUTPUT),
    ]:
        mock.return_value = (text, _mock_result(text))

    decide_dict = json.loads(DECIDE_OUTPUT)
    decide_dict.pop("borderline_decisions", None)
    mock_decide.return_value = (decide_dict, _mock_result(DECIDE_OUTPUT))

    goal = Goal(title="Hash test", description="same goal")
    store.save_goal(goal)
    board = BoardState()
    board.goals.append(goal)
    store.save_board(board)

    r1 = run_gauntlet(goal.id, goal.description, store, client=MagicMock())

    for mock, text in [
        (mock_frame, FRAME_OUTPUT),
        (mock_scope, SCOPE_OUTPUT),
        (mock_arch, ARCH_OUTPUT),
        (mock_challenge, CHALLENGE_OUTPUT),
    ]:
        mock.return_value = (text, _mock_result(text))
    mock_decide.return_value = (dict(decide_dict), _mock_result(DECIDE_OUTPUT))

    r2 = run_gauntlet(goal.id, goal.description, store, client=MagicMock())

    assert r1.locked_plan.locked_hash == r2.locked_plan.locked_hash
