"""Phase K — robustness tests.

Covers atomic writes, file locks, crash recovery, multi-language verify,
and plan integrity verification.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

from agentboard.mcp_server import call_tool
from agentboard.orchestrator.verify import detect_test_runner
from agentboard.storage.file_store import atomic_write, file_lock


def _mcp(tool_name: str, **args):
    async def _run():
        result = await call_tool(tool_name, args)
        text = result[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return asyncio.run(_run())


# ══════════════════════════════════════════════════════════════════════════════
# Atomic writes
# ══════════════════════════════════════════════════════════════════════════════

def test_atomic_write_creates_file(tmp_path: Path):
    atomic_write(tmp_path / "out.json", '{"x":1}')
    assert (tmp_path / "out.json").read_text() == '{"x":1}'


def test_atomic_write_replaces_existing(tmp_path: Path):
    p = tmp_path / "out.txt"
    p.write_text("old")
    atomic_write(p, "new")
    assert p.read_text() == "new"


def test_atomic_write_creates_parents(tmp_path: Path):
    atomic_write(tmp_path / "a" / "b" / "c.txt", "hello")
    assert (tmp_path / "a" / "b" / "c.txt").read_text() == "hello"


def test_atomic_write_no_tmp_residue(tmp_path: Path):
    atomic_write(tmp_path / "out.txt", "hello")
    # No temp files left around
    residue = [p for p in tmp_path.iterdir() if p.name.startswith(".out.txt.")]
    assert not residue


# ══════════════════════════════════════════════════════════════════════════════
# File locks
# ══════════════════════════════════════════════════════════════════════════════

def test_file_lock_serializes_concurrent_writes(tmp_path: Path):
    """Two threads writing to state.json don't corrupt each other."""
    target = tmp_path / "state.json"
    N = 10
    results = []

    def writer(i: int):
        for _ in range(5):
            with file_lock(target):
                # Simulate a small write
                content = {"counter": i, "ts": time.time()}
                atomic_write(target, json.dumps(content))
                results.append(i)
                time.sleep(0.001)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Final file is valid JSON (never partial)
    data = json.loads(target.read_text())
    assert "counter" in data
    # All writes completed
    assert len(results) == N * 5


def test_file_lock_releases_on_exception(tmp_path: Path):
    """If code inside the lock raises, lock is still released."""
    target = tmp_path / "x.json"
    try:
        with file_lock(target):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # Another lock acquisition must succeed immediately
    with file_lock(target):
        atomic_write(target, '{"ok":true}')
    assert target.read_text() == '{"ok":true}'


# ══════════════════════════════════════════════════════════════════════════════
# Multi-language test runner detection
# ══════════════════════════════════════════════════════════════════════════════

def test_detect_runner_pytest_default(tmp_path: Path):
    name, cmd = detect_test_runner(tmp_path)
    assert name == "pytest"
    assert cmd[0] == "pytest"


def test_detect_runner_npm_test(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "x", "scripts": {"test": "vitest run"}
    }))
    name, cmd = detect_test_runner(tmp_path)
    assert name == "npm test"
    assert cmd == ["npm", "test"]


def test_detect_runner_vitest_config(tmp_path: Path):
    (tmp_path / "vitest.config.ts").write_text("export default {}")
    name, cmd = detect_test_runner(tmp_path)
    assert name == "vitest"
    assert "vitest" in " ".join(cmd)


def test_detect_runner_jest_config(tmp_path: Path):
    (tmp_path / "jest.config.js").write_text("module.exports = {}")
    name, cmd = detect_test_runner(tmp_path)
    assert name == "jest"


def test_detect_runner_go_mod(tmp_path: Path):
    (tmp_path / "go.mod").write_text("module x\ngo 1.21")
    name, cmd = detect_test_runner(tmp_path)
    assert name == "go test"
    assert cmd == ["go", "test", "./..."]


def test_detect_runner_cargo(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"')
    name, cmd = detect_test_runner(tmp_path)
    assert name == "cargo test"


def test_detect_runner_package_json_priority(tmp_path: Path):
    """package.json with test script should win over bare vitest.config."""
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": "npm exec vitest"}
    }))
    (tmp_path / "vitest.config.js").write_text("export default {}")
    name, cmd = detect_test_runner(tmp_path)
    assert name == "npm test"


# ══════════════════════════════════════════════════════════════════════════════
# Plan integrity
# ══════════════════════════════════════════════════════════════════════════════

def _lock_a_plan(tmp_path: Path) -> str:
    """Helper — init + add goal + approve + lock plan, return goal_id."""
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="Calc", description="calc")
    goal_id = r["goal_id"]
    _mcp("agentboard_approve_plan", project_root=root, goal_id=goal_id, approved=True)
    _mcp("agentboard_lock_plan", project_root=root, goal_id=goal_id, decide_json={
        "problem": "calc", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "x", "known_failure_modes": [],
        "goal_checklist": ["add works"], "out_of_scope_guard": [],
        "atomic_steps": [],
        "token_ceiling": 100_000, "max_iterations": 3,
    })
    return goal_id


def test_plan_integrity_ok_after_lock(tmp_path: Path):
    goal_id = _lock_a_plan(tmp_path)
    r = _mcp("agentboard_verify_plan_integrity",
             project_root=str(tmp_path), goal_id=goal_id)
    assert r["integrity_ok"] is True
    assert r["stored_hash"] == r["computed_hash"]


def test_plan_integrity_missing_plan(tmp_path: Path):
    """Goal without a locked plan should return error."""
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="X", description="x")
    result = _mcp("agentboard_verify_plan_integrity",
                  project_root=root, goal_id=r["goal_id"])
    assert "error" in result


# ══════════════════════════════════════════════════════════════════════════════
# Crash recovery — resume_run
# ══════════════════════════════════════════════════════════════════════════════

def test_resume_run_mid_flight(tmp_path: Path):
    """Simulate crash after tdd_red_complete; resume should say GREEN next."""
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="x", description="x")
    goal_id = r["goal_id"]
    _mcp("agentboard_approve_plan", project_root=root, goal_id=goal_id, approved=True)
    _mcp("agentboard_lock_plan", project_root=root, goal_id=goal_id, decide_json={
        "problem": "x", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "x", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "atomic_steps": [], "token_ceiling": 100_000, "max_iterations": 3,
    })
    r = _mcp("agentboard_start_task", project_root=root, goal_id=goal_id)
    run_id = r["run_id"]

    # Simulate progress up to RED
    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="tdd_red_complete",
         state={"iteration": 1, "current_step_id": "s_001"})

    # Resume — should say we can continue, and that GREEN is next
    result = _mcp("agentboard_resume_run", project_root=root, run_id=run_id)
    assert result["can_resume"] is True
    assert result["last_event"] == "tdd_red_complete"
    assert "GREEN" in result["resume_hint"]


def test_resume_run_after_converged(tmp_path: Path):
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    r = _mcp("agentboard_add_goal", project_root=root, title="x", description="x")
    goal_id = r["goal_id"]
    _mcp("agentboard_approve_plan", project_root=root, goal_id=goal_id, approved=True)
    _mcp("agentboard_lock_plan", project_root=root, goal_id=goal_id, decide_json={
        "problem": "x", "non_goals": [], "scope_decision": "HOLD",
        "architecture": "x", "known_failure_modes": [],
        "goal_checklist": ["x"], "out_of_scope_guard": [],
        "atomic_steps": [], "token_ceiling": 100_000, "max_iterations": 3,
    })
    r = _mcp("agentboard_start_task", project_root=root, goal_id=goal_id)
    run_id = r["run_id"]

    _mcp("agentboard_checkpoint", project_root=root, run_id=run_id,
         event="converged", state={"iterations": 3})

    result = _mcp("agentboard_resume_run", project_root=root, run_id=run_id)
    assert result["can_resume"] is False
    assert result["last_event"] == "converged"


def test_resume_nonexistent_run(tmp_path: Path):
    root = str(tmp_path)
    _mcp("agentboard_init", project_root=root)
    result = _mcp("agentboard_resume_run", project_root=root, run_id="run_bogus")
    assert "error" in result


# ══════════════════════════════════════════════════════════════════════════════
# All tools count bump after Phase K additions
# ══════════════════════════════════════════════════════════════════════════════

def test_mcp_tools_after_phase_k():
    import asyncio
    from agentboard.mcp_server import list_tools
    tools = asyncio.run(list_tools())
    names = {t.name for t in tools}
    # New Phase I + K tools
    assert "agentboard_start_task" in names
    assert "agentboard_checkpoint" in names
    assert "agentboard_resume_run" in names
    assert "agentboard_verify_plan_integrity" in names
