from __future__ import annotations

import json

from devboard.models import AtomicStep, LockedPlan


def build_locked_plan(goal_id: str, decide_json: dict) -> LockedPlan:
    atomic_steps_raw = decide_json.get("atomic_steps", [])
    atomic_steps = []
    for i, s in enumerate(atomic_steps_raw):
        if isinstance(s, dict):
            atomic_steps.append(AtomicStep(
                id=s.get("id") or f"s_{i+1:03d}",
                behavior=s.get("behavior", ""),
                test_file=s.get("test_file", ""),
                test_name=s.get("test_name", ""),
                impl_file=s.get("impl_file", ""),
                expected_fail_reason=s.get("expected_fail_reason", ""),
            ))

    plan = LockedPlan(
        goal_id=goal_id,
        problem=decide_json.get("problem", ""),
        non_goals=decide_json.get("non_goals", []),
        scope_decision=decide_json.get("scope_decision", "HOLD"),
        architecture=decide_json.get("architecture", ""),
        known_failure_modes=decide_json.get("known_failure_modes", []),
        goal_checklist=decide_json.get("goal_checklist", []),
        out_of_scope_guard=decide_json.get("out_of_scope_guard", []),
        atomic_steps=atomic_steps,
        token_ceiling=decide_json.get("token_ceiling", 300_000),
        max_iterations=min(max(decide_json.get("max_iterations", 5), 2), 10),
    )
    return plan.lock()


def parse_decide_output(text: str) -> dict:
    """Extract JSON from decide step output, tolerating markdown fences."""
    text = text.strip()
    # Find first { and last } regardless of fences or surrounding prose
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)
