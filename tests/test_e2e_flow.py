"""End-to-end integration test — simulates the exact sequence of MCP tool
calls that a well-behaved Claude Code session running the devboard skills
would produce. Asserts the resulting .devboard/ state is well-formed and
complete (no missing phases, all required files present, correct hashes).

This is what Phase I-3 guarantees: even before testing with real Claude Code,
we know the MCP plumbing and state model are internally consistent.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agentboard.mcp_server import call_tool


def _mcp(tool_name: str, **args):
    async def _run():
        result = await call_tool(tool_name, args)
        text = result[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return asyncio.run(_run())


def _decide_json(goal_title: str = "Build calculator") -> dict:
    return {
        "problem": goal_title,
        "non_goals": ["gui", "multi-language"],
        "scope_decision": "HOLD",
        "architecture": "Single calculator.py with add/sub/mul/div functions. Pure functions.",
        "known_failure_modes": ["CRITICAL: div by zero", "HIGH: int vs float"],
        "goal_checklist": [
            "add() returns sum",
            "sub() returns difference",
            "div() raises ZeroDivisionError on zero divisor",
        ],
        "out_of_scope_guard": ["src/payments/", "src/auth/"],
        "atomic_steps": [
            {
                "id": "s_001", "behavior": "add(1,2)==3",
                "test_file": "tests/test_calc.py", "test_name": "test_add",
                "impl_file": "calculator.py", "expected_fail_reason": "NameError",
            },
            {
                "id": "s_002", "behavior": "sub(5,2)==3",
                "test_file": "tests/test_calc.py", "test_name": "test_sub",
                "impl_file": "calculator.py", "expected_fail_reason": "AttributeError",
            },
            {
                "id": "s_003", "behavior": "div(1,0) raises ZeroDivisionError",
                "test_file": "tests/test_calc.py", "test_name": "test_div_zero",
                "impl_file": "calculator.py", "expected_fail_reason": "AssertionError",
            },
        ],
        "token_ceiling": 100_000,
        "max_iterations": 3,
    }


# ══════════════════════════════════════════════════════════════════════════════
# E2E: full Gauntlet → TDD → CSO → Red-team → Approval flow
# ══════════════════════════════════════════════════════════════════════════════

def test_e2e_full_flow(tmp_path: Path):
    root = str(tmp_path)

    # Step 1 — init
    r = _mcp("agentboard_init", project_root=root)
    assert r["status"] == "initialized"
    assert (tmp_path / ".devboard").exists()

    # Step 2 — add goal
    r = _mcp("agentboard_add_goal", project_root=root,
             title="Calculator", description="Calculator with add/sub/div")
    goal_id = r["goal_id"]
    assert goal_id

    # Step 3 — approve plan then lock
    _mcp("agentboard_approve_plan", project_root=root, goal_id=goal_id, approved=True)
    r = _mcp("agentboard_lock_plan", project_root=root,
             goal_id=goal_id, decide_json=_decide_json("Calculator"))
    locked_hash = r["locked_hash"]
    assert locked_hash
    assert r["atomic_steps_count"] == 3
    assert Path(r["plan_path"]).exists()

    # Step 4 — start task + run
    r = _mcp("agentboard_start_task", project_root=root, goal_id=goal_id)
    task_id = r["task_id"]
    run_id = r["run_id"]
    assert task_id and run_id
    run_file = tmp_path / ".devboard" / "runs" / f"{run_id}.jsonl"
    assert run_file.exists()

    # Step 5 — checkpoint gauntlet complete
    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="gauntlet_complete", state={"locked_hash": locked_hash, "atomic_steps": 3})

    # Step 6 — TDD cycles for each atomic step
    for i, step in enumerate(_decide_json()["atomic_steps"], start=1):
        # RED
        _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
             event="tdd_red_complete",
             state={"iteration": i, "current_step_id": step["id"], "status": "RED_CONFIRMED"})
        _mcp("agentboard_log_decision", project_root=root, task_id=task_id,
             iter=i, phase="tdd_red",
             reasoning=f"Wrote failing test {step['test_name']}",
             verdict_source="RED_CONFIRMED")

        # GREEN
        _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
             event="tdd_green_complete",
             state={"iteration": i, "current_step_id": step["id"], "status": "GREEN_CONFIRMED"})
        _mcp("agentboard_log_decision", project_root=root, task_id=task_id,
             iter=i, phase="tdd_green",
             reasoning=f"Implemented minimal code for {step['behavior']}",
             verdict_source="GREEN_CONFIRMED")

        # REFACTOR (SKIPPED for simplicity)
        _mcp("agentboard_log_decision", project_root=root, task_id=task_id,
             iter=i, phase="tdd_refactor",
             reasoning="no duplication", verdict_source="SKIPPED")

        # iter diff (simulated)
        _mcp("agentboard_save_iter_diff", project_root=root, task_id=task_id,
             iter_n=i, diff=f"+ def {step['test_name']}() ...\n")

    # Step 7 — tdd complete
    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="tdd_complete", state={"total_iterations": 3, "checklist_verified": True})

    # Step 8 — review pass
    _mcp("agentboard_log_decision", project_root=root, task_id=task_id,
         iter=3, phase="review", reasoning="All checklist items verified",
         verdict_source="PASS")

    # Step 9 — CSO: diff has no security keywords, skipped
    # (skill would call agentboard_get_diff_stats first, see nothing, and skip)

    # Step 10 — Red-team: SURVIVED
    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="redteam_complete", state={"survived": True, "scenarios_count": 3})
    _mcp("agentboard_log_decision", project_root=root, task_id=task_id,
         iter=3, phase="redteam", reasoning="3 attack scenarios probed, all mitigated",
         verdict_source="SURVIVED")

    # Step 11 — converged
    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="converged", state={"iterations": 3, "ready_for_approval": True})

    # ── Assertions ──────────────────────────────────────────────────────────

    # Plan files exist
    plan_dir = tmp_path / ".devboard" / "goals" / goal_id
    assert (plan_dir / "plan.md").exists()
    assert (plan_dir / "plan.json").exists()

    # Run file has all expected events in order
    events = [json.loads(l)["event"] for l in run_file.read_text().splitlines() if l.strip()]
    expected_events_subset = [
        "run_start",
        "gauntlet_complete",
        "tdd_red_complete",  # iter 1
        "tdd_green_complete",
        "tdd_red_complete",  # iter 2
        "tdd_green_complete",
        "tdd_red_complete",  # iter 3
        "tdd_green_complete",
        "tdd_complete",
        "redteam_complete",
        "converged",
    ]
    assert events == expected_events_subset, f"Event sequence mismatch:\n{events}"

    # Decisions.jsonl should have 3*3 + 1 (review) + 1 (redteam) = 11 entries
    decisions = _mcp("agentboard_load_decisions", project_root=root, task_id=task_id)
    assert isinstance(decisions, list)
    assert len(decisions) == 11

    # Distinct phases logged
    phases = {d["phase"] for d in decisions}
    assert phases == {"tdd_red", "tdd_green", "tdd_refactor", "review", "redteam"}

    # Iter diffs saved
    changes_dir = plan_dir / "tasks" / task_id / "changes"
    assert changes_dir.exists()
    assert (changes_dir / "iter_1.diff").exists()
    assert (changes_dir / "iter_2.diff").exists()
    assert (changes_dir / "iter_3.diff").exists()


# ══════════════════════════════════════════════════════════════════════════════
# E2E: replay flow — branch from past iteration
# ══════════════════════════════════════════════════════════════════════════════

def test_e2e_replay_flow(tmp_path: Path):
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="T", description="x")
    goal_id = r["goal_id"]
    _mcp("agentboard_approve_plan", project_root=root, goal_id=goal_id, approved=True)
    _mcp("agentboard_lock_plan", project_root=root, goal_id=goal_id, decide_json=_decide_json())
    r = _mcp("agentboard_start_task", project_root=root, goal_id=goal_id)
    task_id, run_id = r["task_id"], r["run_id"]

    # Simulate reaching iter 2 then stuck
    for i in [1, 2]:
        _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
             event="iteration_complete",
             state={"iteration": i, "goal_id": goal_id, "task_id": task_id,
                    "history": [{"n": j} for j in range(1, i + 1)]})

    # Replay from iter 1
    r = _mcp("agentboard_replay", project_root=root,
             source_run_id=run_id, from_iteration=1, variant_note="try iterative instead")
    assert "new_run_id" in r
    assert r["new_run_id"].startswith("replay_")
    new_run_path = tmp_path / ".devboard" / "runs" / f"{r['new_run_id']}.jsonl"
    assert new_run_path.exists()

    # Source run untouched
    source_path = tmp_path / ".devboard" / "runs" / f"{run_id}.jsonl"
    assert source_path.exists()


# ══════════════════════════════════════════════════════════════════════════════
# E2E: RCA escalation after 3 consecutive failures
# ══════════════════════════════════════════════════════════════════════════════

def test_e2e_rca_escalation(tmp_path: Path):
    """Simulate a goal where TDD keeps RETRYing on the same symptom 3+ times."""
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="Stuck", description="y")
    goal_id = r["goal_id"]
    _mcp("agentboard_approve_plan", project_root=root, goal_id=goal_id, approved=True)
    _mcp("agentboard_lock_plan", project_root=root, goal_id=goal_id, decide_json=_decide_json())
    r = _mcp("agentboard_start_task", project_root=root, goal_id=goal_id)
    task_id, run_id = r["task_id"], r["run_id"]

    # Three RETRY + reflect cycles on the same symptom
    for i in [1, 2, 3]:
        _mcp("agentboard_log_decision", project_root=root, task_id=task_id,
             iter=i, phase="review", reasoning="same failure: div by zero not caught",
             verdict_source="RETRY")
        _mcp("agentboard_log_decision", project_root=root, task_id=task_id,
             iter=i, phase="reflect",
             reasoning="div not handling zero", next_strategy="add guard",
             verdict_source="RCA_DONE" if i < 3 else "RCA_ESCALATED")

    # On the 3rd, RCA should escalate
    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="blocked", state={"reason": "RCA escalation — rethink needed", "consecutive_failures": 3})

    decisions = _mcp("agentboard_load_decisions", project_root=root, task_id=task_id)
    escalated = [d for d in decisions if d["verdict_source"] == "RCA_ESCALATED"]
    assert len(escalated) == 1


# ══════════════════════════════════════════════════════════════════════════════
# E2E: iron law detector on simulated tool_call sequences
# ══════════════════════════════════════════════════════════════════════════════

def test_e2e_iron_law_detector():
    """Real flow: skill passes tool_calls to check_iron_law at end of GREEN."""
    # Good: test written first, then impl
    r = _mcp("agentboard_check_iron_law", tool_calls=[
        {"tool_name": "fs_write", "tool_input": {"path": "tests/test_x.py", "content": "..."}},
        {"tool_name": "shell", "tool_input": {"command": "pytest"}},
        {"tool_name": "fs_write", "tool_input": {"path": "x.py", "content": "..."}},
    ])
    assert not r["violated"]

    # Bad: impl first, no test
    r = _mcp("agentboard_check_iron_law", tool_calls=[
        {"tool_name": "fs_write", "tool_input": {"path": "x.py", "content": "..."}},
    ])
    assert r["violated"]


# ══════════════════════════════════════════════════════════════════════════════
# E2E: full checkpoint sequence produces valid watch output
# ══════════════════════════════════════════════════════════════════════════════

def test_e2e_watch_sees_run(tmp_path: Path):
    """After a run is created + checkpointed, the watch command would find it."""
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="W", description="x")
    goal_id = r["goal_id"]
    _mcp("agentboard_approve_plan", project_root=root, goal_id=goal_id, approved=True)
    _mcp("agentboard_lock_plan", project_root=root, goal_id=goal_id, decide_json=_decide_json())
    r = _mcp("agentboard_start_task", project_root=root, goal_id=goal_id)
    run_id = r["run_id"]

    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="tdd_red_complete", state={"iteration": 1})

    runs = _mcp("agentboard_list_runs", project_root=root)
    assert isinstance(runs, list)
    assert any(r["run_id"] == run_id for r in runs)

    # Run has at least run_start + our checkpoint = 2 events
    our_run = next(r for r in runs if r["run_id"] == run_id)
    assert our_run["events"] >= 2


# ══════════════════════════════════════════════════════════════════════════════
# E2E: learnings flow — save + search + retrieve
# ══════════════════════════════════════════════════════════════════════════════

def test_e2e_learnings_lifecycle(tmp_path: Path):
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)

    # RCA skill saves a learning after a CRITICAL bug
    _mcp("agentboard_save_learning", project_root=root,
         name="zero_div_guard",
         content="Always handle ZeroDivisionError explicitly. Python's default crashes.",
         tags=["python", "arithmetic", "error-handling"],
         category="pattern",
         confidence=0.85)

    # Gauntlet skill searches for relevant learnings at Frame step
    results = _mcp("agentboard_search_learnings", project_root=root,
                   query="division")
    assert len(results) == 1
    assert results[0]["confidence"] == 0.85

    # Retriever picks it up for a goal description
    r = _mcp("agentboard_relevant_learnings", project_root=root,
             goal_description="Build a calculator with division that handles zero divisor")
    assert "zero_div_guard" in r["markdown"]
    assert "ZeroDivisionError" in r["markdown"]


# ══════════════════════════════════════════════════════════════════════════════
# E2E: CSO + diff-based auto-trigger
# ══════════════════════════════════════════════════════════════════════════════

def test_e2e_command_safety_gate(tmp_path: Path):
    """Skills use check_command_safety BEFORE running bash."""
    r = _mcp("agentboard_check_command_safety", command="rm -rf /")
    assert r["level"] == "block"

    r = _mcp("agentboard_check_command_safety", command="git push --force")
    assert r["level"] == "warn"

    r = _mcp("agentboard_check_command_safety", command="pytest tests/")
    assert r["level"] == "safe"
