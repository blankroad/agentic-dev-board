from __future__ import annotations

import json

from agentboard.gauntlet.lock import build_locked_plan, parse_decide_output


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


def test_locked_plan_integration_command_defaults_empty():
    from agentboard.models import LockedPlan
    plan = LockedPlan(goal_id="g_x")
    assert plan.integration_test_command == ""


def test_hash_excludes_integration_command():
    from agentboard.models import LockedPlan
    plan_empty = LockedPlan(goal_id="g_x", problem="p", atomic_steps=[])
    plan_with = LockedPlan(
        goal_id="g_x", problem="p", atomic_steps=[],
        integration_test_command="pytest tests/e2e",
    )
    assert plan_empty.compute_hash() == plan_with.compute_hash()


def test_build_locked_plan_reads_integration_command():
    parsed = parse_decide_output(DECIDE_OUTPUT)
    parsed.pop("borderline_decisions", None)
    parsed["integration_test_command"] = "make smoke"
    plan = build_locked_plan("g_x", parsed)
    assert plan.integration_test_command == "make smoke"


def test_locked_plan_hash_deterministic():
    parsed = parse_decide_output(DECIDE_OUTPUT)
    parsed.pop("borderline_decisions", None)
    plan1 = build_locked_plan("g_001", dict(parsed))
    plan2 = build_locked_plan("g_001", dict(parsed))
    assert plan1.locked_hash == plan2.locked_hash


def test_locked_plan_hash_changes_when_atomic_steps_change():
    """atomic_steps mutation must invalidate the stored hash."""
    parsed = parse_decide_output(DECIDE_OUTPUT)
    parsed.pop("borderline_decisions", None)
    plan = build_locked_plan("g_001", dict(parsed))
    original_hash = plan.compute_hash()

    # Mutate an atomic step and recompute
    if plan.atomic_steps:
        plan.atomic_steps[0].behavior = "MUTATED_BY_TEST"
    else:
        from agentboard.models import AtomicStep
        plan.atomic_steps = [AtomicStep(id="s_mut", behavior="injected", test_file="tests/t.py", test_name="t")]

    new_hash = plan.compute_hash()
    assert original_hash != new_hash, "Hash must differ after atomic_steps mutation"


def test_max_iterations_clamped():
    data = json.loads(DECIDE_OUTPUT)
    data["max_iterations"] = 50
    data.pop("borderline_decisions", None)
    plan = build_locked_plan("g_001", data)
    assert plan.max_iterations == 10

    data["max_iterations"] = 1
    plan2 = build_locked_plan("g_001", data)
    assert plan2.max_iterations == 2

