"""Validation that agentboard_checkpoint warns on out-of-order events and
auto-updates task state on terminal events."""
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


def _seed(tmp_path: Path) -> tuple[str, str, str]:
    """Seed init + goal + plan + start_task. Returns (goal_id, task_id, run_id)."""
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="T", description="t")
    goal_id = r["goal_id"]
    _mcp("agentboard_lock_plan", project_root=root, goal_id=goal_id, decide_json={
        "problem": "x", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "atomic_steps": [], "token_ceiling": 100_000, "max_iterations": 5,
    })
    r = _mcp("agentboard_start_task", project_root=root, goal_id=goal_id)
    return goal_id, r["task_id"], r["run_id"]


# ── Order validation ──────────────────────────────────────────────────────────

def test_green_without_red_warns(tmp_path: Path):
    _, _, run_id = _seed(tmp_path)
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_green_complete", state={"iteration": 1})
    assert r["warnings"]
    assert any("tdd_red_complete" in w for w in r["warnings"])


def test_green_with_prior_red_ok(tmp_path: Path):
    _, _, run_id = _seed(tmp_path)
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_red_complete", state={"iteration": 1})
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_green_complete", state={"iteration": 1})
    assert r["warnings"] == []


def test_refactor_without_green_warns(tmp_path: Path):
    _, _, run_id = _seed(tmp_path)
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_refactor_complete", state={"iteration": 1})
    assert any("tdd_green_complete" in w for w in r["warnings"])


def test_refactor_with_green_ok(tmp_path: Path):
    _, _, run_id = _seed(tmp_path)
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_red_complete", state={"iteration": 1})
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_green_complete", state={"iteration": 1})
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_refactor_complete", state={"iteration": 1})
    assert r["warnings"] == []


def test_converged_without_tdd_warns(tmp_path: Path):
    _, _, run_id = _seed(tmp_path)
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="converged", state={})
    assert any("tdd" in w.lower() for w in r["warnings"])


def test_converged_after_tdd_complete_ok(tmp_path: Path):
    _, _, run_id = _seed(tmp_path)
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_complete", state={})
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="converged", state={})
    assert r["warnings"] == []


def test_multiple_iterations_each_need_own_red(tmp_path: Path):
    """Iter 1 RED + GREEN, then iter 2 GREEN without RED — warns for iter 2."""
    _, _, run_id = _seed(tmp_path)
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_red_complete", state={"iteration": 1})
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_green_complete", state={"iteration": 1})
    # iter 2 directly green — should warn
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_green_complete", state={"iteration": 2})
    assert any("iter 2" in w for w in r["warnings"])


def test_save_succeeds_even_with_warnings(tmp_path: Path):
    """Validation warns but does not block."""
    _, _, run_id = _seed(tmp_path)
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_green_complete", state={"iteration": 1})
    assert r["status"] == "saved"   # still saved despite warning


# ── Side-effect: task state auto-update ───────────────────────────────────────

def test_converged_updates_task_status(tmp_path: Path):
    goal_id, task_id, run_id = _seed(tmp_path)

    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_complete", state={"task_id": task_id})
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="converged", state={"task_id": task_id, "iterations": 3})

    # task should now be converged + converged=True
    from agentboard.storage.file_store import FileStore
    store = FileStore(tmp_path)
    task = store.load_task(goal_id, task_id)
    assert task is not None
    assert task.converged is True
    assert task.status.value == "converged"


def test_blocked_updates_task_status(tmp_path: Path):
    goal_id, task_id, run_id = _seed(tmp_path)

    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="blocked", state={"task_id": task_id, "reason": "stuck"})

    from agentboard.storage.file_store import FileStore
    store = FileStore(tmp_path)
    task = store.load_task(goal_id, task_id)
    assert task.converged is False
    assert task.status.value == "blocked"


def test_converged_finds_task_id_from_prior_run_start(tmp_path: Path):
    """Even if state dict doesn't include task_id, checkpoint finds it from run_start."""
    goal_id, task_id, run_id = _seed(tmp_path)
    # run_start event already has task_id from agentboard_start_task
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="tdd_complete", state={})
    r = _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event="converged", state={})  # no task_id in state

    from agentboard.storage.file_store import FileStore
    store = FileStore(tmp_path)
    task = store.load_task(goal_id, task_id)
    assert task.converged is True
