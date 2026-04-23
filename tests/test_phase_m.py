"""Phase M — metrics + diagnostics."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agentboard.mcp_server import call_tool
from agentboard.analytics.metrics import collect_metrics, diagnose_activations
from agentboard.models import BoardState, DecisionEntry, Goal, GoalStatus, Task
from agentboard.storage.file_store import FileStore


def _mcp(tool_name: str, **args):
    async def _run():
        result = await call_tool(tool_name, args)
        text = result[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return asyncio.run(_run())


def _seed_project(tmp_path: Path) -> tuple[FileStore, str, str]:
    """Seed a project with 1 goal, 1 task, and some decisions + a run."""
    _mcp("agentboard_init", project_root=str(tmp_path))
    r = _mcp("agentboard_add_goal", project_root=str(tmp_path),
             title="Test", description="test")
    goal_id = r["goal_id"]
    _mcp("agentboard_lock_plan", project_root=str(tmp_path), goal_id=goal_id, decide_json={
        "problem": "x", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "a", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "atomic_steps": [], "token_ceiling": 100_000, "max_iterations": 3,
    })
    r = _mcp("agentboard_start_task", project_root=str(tmp_path), goal_id=goal_id)
    task_id, run_id = r["task_id"], r["run_id"]
    store = FileStore(tmp_path)
    return store, task_id, run_id


def test_metrics_empty_project(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".agentboard").mkdir()
    store.save_board(BoardState())
    m = collect_metrics(store)
    assert m.total_goals == 0
    assert m.total_runs == 0
    assert m.convergence_rate == 0.0


def test_metrics_counts_events(tmp_path: Path):
    store, task_id, run_id = _seed_project(tmp_path)
    # Produce events
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="gauntlet_complete", state={})
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_red_complete", state={"iteration": 1})
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_green_complete", state={"iteration": 1})
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="converged", state={})

    m = collect_metrics(store)
    assert m.total_goals == 1
    assert m.total_runs == 1
    assert m.converged_runs == 1
    assert m.convergence_rate == 1.0
    assert m.skill_events_by_type["gauntlet_complete"] == 1
    assert m.skill_events_by_type["tdd_red_complete"] == 1


def test_metrics_retry_tracking(tmp_path: Path):
    store, task_id, _ = _seed_project(tmp_path)
    for i in [1, 2]:
        _mcp("agentboard_log_decision", project_root=str(tmp_path), task_id=task_id,
             iter=i, phase="review", reasoning="x", verdict_source="RETRY")
    _mcp("agentboard_log_decision", project_root=str(tmp_path), task_id=task_id,
         iter=3, phase="review", reasoning="x", verdict_source="PASS")

    m = collect_metrics(store)
    assert m.total_retries == 2
    assert m.total_passes == 1
    assert m.retry_rate == pytest.approx(2 / 3)


def test_metrics_iron_law_hits(tmp_path: Path):
    store, task_id, _ = _seed_project(tmp_path)
    _mcp("agentboard_log_decision", project_root=str(tmp_path), task_id=task_id,
         iter=1, phase="iron_law", reasoning="impl before test", verdict_source="iron_law")
    _mcp("agentboard_log_decision", project_root=str(tmp_path), task_id=task_id,
         iter=2, phase="iron_law", reasoning="again", verdict_source="iron_law")

    m = collect_metrics(store)
    assert m.iron_law_hits == 2


def test_metrics_markdown_renders(tmp_path: Path):
    store, _, _ = _seed_project(tmp_path)
    m = collect_metrics(store)
    md = m.to_markdown()
    assert "# Metrics Report" in md
    assert "Top-line" in md


def test_metrics_dict_structure(tmp_path: Path):
    store, _, _ = _seed_project(tmp_path)
    m = collect_metrics(store)
    d = m.to_dict()
    assert "total_goals" in d
    assert "convergence_rate" in d
    assert "skill_events" in d


# ══════════════════════════════════════════════════════════════════════════════
# Diagnose
# ══════════════════════════════════════════════════════════════════════════════

def test_diagnose_empty_project_suggests_action(tmp_path: Path):
    store = FileStore(tmp_path)
    (tmp_path / ".agentboard").mkdir()
    store.save_board(BoardState())
    r = diagnose_activations(store)
    assert r.skill_activation_score == 0.0
    assert len(r.missing_events) > 0
    assert any("Claude Code" in s or "explicit invocation" in s for s in r.suggestions)


def test_diagnose_partial_activation(tmp_path: Path):
    store, _, run_id = _seed_project(tmp_path)
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="gauntlet_complete", state={})
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="tdd_red_complete", state={"iteration": 1})

    r = diagnose_activations(store)
    assert 0 < r.skill_activation_score < 1.0
    assert "tdd_green_complete" in r.missing_events


def test_diagnose_all_events_good(tmp_path: Path):
    store, _, run_id = _seed_project(tmp_path)
    for event in [
        "gauntlet_complete", "tdd_red_complete", "tdd_green_complete",
        "tdd_refactor_complete", "review_complete", "tdd_complete",
        "redteam_complete", "converged",
    ]:
        _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
             event=event, state={})

    r = diagnose_activations(store)
    assert r.skill_activation_score == 1.0
    assert r.missing_events == []


def test_diagnose_suggests_rca_concerns(tmp_path: Path):
    store, task_id, run_id = _seed_project(tmp_path)
    _mcp("agentboard_checkpoint", project_root=str(tmp_path), run_id=run_id,
         event="gauntlet_complete", state={})
    _mcp("agentboard_log_decision", project_root=str(tmp_path), task_id=task_id,
         iter=1, phase="reflect", reasoning="x", verdict_source="RCA_ESCALATED")

    r = diagnose_activations(store)
    assert any("RCA escalation" in s for s in r.suggestions)


# ══════════════════════════════════════════════════════════════════════════════
# MCP tool access
# ══════════════════════════════════════════════════════════════════════════════

def test_mcp_metrics_tool(tmp_path: Path):
    _seed_project(tmp_path)
    r = _mcp("agentboard_metrics", project_root=str(tmp_path))
    assert "dict" in r
    assert "markdown" in r
    assert r["dict"]["total_goals"] == 1


def test_mcp_diagnose_tool(tmp_path: Path):
    _seed_project(tmp_path)
    r = _mcp("agentboard_diagnose", project_root=str(tmp_path))
    assert "skill_activation_score" in r
    assert "suggestions" in r
    assert "markdown" in r
