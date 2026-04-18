"""MCP server + install tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from devboard.install import (
    emit_mcp_config,
    emit_settings_hooks,
    install_hooks,
    install_skills,
    install_all,
)


# ══════════════════════════════════════════════════════════════════════════════
# MCP server — tool listing + dispatch
# ══════════════════════════════════════════════════════════════════════════════

def test_mcp_server_lists_tools():
    """Smoke: the server's list_tools returns all expected tools."""
    import asyncio
    from devboard.mcp_server import list_tools

    tools = asyncio.run(list_tools())
    names = {t.name for t in tools}

    expected_minimum = {
        "devboard_init", "devboard_add_goal", "devboard_list_goals",
        "devboard_lock_plan", "devboard_load_plan",
        "devboard_log_decision", "devboard_load_decisions", "devboard_save_iter_diff",
        "devboard_verify", "devboard_check_iron_law", "devboard_check_command_safety",
        "devboard_get_diff_stats", "devboard_build_pr_body",
        "devboard_apply_squash_policy", "devboard_push_pr",
        "devboard_save_learning", "devboard_search_learnings", "devboard_relevant_learnings",
        "devboard_generate_retro", "devboard_list_runs", "devboard_replay",
        "devboard_save_brainstorm", "devboard_approve_plan",
    }
    missing = expected_minimum - names
    assert not missing, f"MCP tools missing: {missing}"


def test_mcp_all_tools_have_schema():
    import asyncio
    from devboard.mcp_server import list_tools

    tools = asyncio.run(list_tools())
    for t in tools:
        assert t.name
        assert t.description
        assert t.inputSchema is not None
        assert t.inputSchema.get("type") == "object"


# ── Dispatch smoke tests ──────────────────────────────────────────────────────

def _dispatch_sync(tool_name: str, args: dict):
    import asyncio
    from devboard.mcp_server import call_tool
    return asyncio.run(call_tool(tool_name, args))


def _json_payload(result):
    # result is list[TextContent]; extract text and json.loads if possible
    text = result[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def test_mcp_init_creates_devboard_dir(tmp_path: Path):
    result = _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    payload = _json_payload(result)
    assert payload["status"] == "initialized"
    assert (tmp_path / ".devboard").exists()
    assert (tmp_path / ".devboard" / "goals").is_dir()
    assert (tmp_path / ".devboard" / "runs").is_dir()


def test_mcp_init_is_idempotent(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    result = _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    payload = _json_payload(result)
    assert payload["status"] == "already_initialized"


def test_mcp_add_goal_and_list(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    result = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path),
        "title": "Test goal", "description": "Build a calculator",
    })
    payload = _json_payload(result)
    assert payload["active"] is True
    goal_id = payload["goal_id"]

    result2 = _dispatch_sync("devboard_list_goals", {"project_root": str(tmp_path)})
    payload2 = _json_payload(result2)
    assert len(payload2["goals"]) == 1
    assert payload2["goals"][0]["id"] == goal_id


def test_mcp_lock_plan_computes_hash(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path),
        "title": "calc", "description": "Build a calculator",
    })
    goal_id = _json_payload(add)["goal_id"]

    _dispatch_sync("devboard_approve_plan", {
        "project_root": str(tmp_path), "goal_id": goal_id, "approved": True,
    })

    result = _dispatch_sync("devboard_lock_plan", {
        "project_root": str(tmp_path),
        "goal_id": goal_id,
        "decide_json": {
            "problem": "Build a calculator",
            "non_goals": [],
            "scope_decision": "HOLD",
            "architecture": "Single calculator.py",
            "known_failure_modes": [],
            "goal_checklist": ["add works", "sub works"],
            "out_of_scope_guard": [],
            "atomic_steps": [
                {"id": "s_001", "behavior": "add(1,2)==3",
                 "test_file": "tests/test_calc.py", "test_name": "test_add",
                 "impl_file": "calc.py"},
            ],
            "token_ceiling": 100_000,
            "max_iterations": 3,
        },
    })
    payload = _json_payload(result)
    assert payload["locked_hash"]
    assert payload["goal_checklist_count"] == 2
    assert payload["atomic_steps_count"] == 1
    assert Path(payload["plan_path"]).exists()


def test_mcp_log_and_load_decisions(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path), "title": "x", "description": "y",
    })
    goal_id = _json_payload(add)["goal_id"]

    # Manually create a task for this goal so append_decision can find it
    from devboard.models import Task
    from devboard.storage.file_store import FileStore
    store = FileStore(tmp_path)
    board = store.load_board()
    task = Task(goal_id=goal_id, title="t")
    board.goals[0].task_ids.append(task.id)
    store.save_task(task)
    store.save_board(board)

    _dispatch_sync("devboard_log_decision", {
        "project_root": str(tmp_path),
        "task_id": task.id, "iter": 1, "phase": "tdd_red",
        "reasoning": "wrote failing test for add",
        "verdict_source": "RED_CONFIRMED",
    })
    _dispatch_sync("devboard_log_decision", {
        "project_root": str(tmp_path),
        "task_id": task.id, "iter": 1, "phase": "tdd_green",
        "reasoning": "minimal impl passes",
        "verdict_source": "GREEN_CONFIRMED",
    })

    result = _dispatch_sync("devboard_load_decisions", {
        "project_root": str(tmp_path), "task_id": task.id,
    })
    payload = _json_payload(result)
    assert len(payload) == 2
    assert payload[0]["phase"] == "tdd_red"
    assert payload[1]["verdict_source"] == "GREEN_CONFIRMED"


def test_mcp_check_iron_law_detects_violation():
    result = _dispatch_sync("devboard_check_iron_law", {
        "tool_calls": [
            {"tool_name": "fs_write", "tool_input": {"path": "calc.py", "content": "x"}},
        ],
    })
    payload = _json_payload(result)
    assert payload["violated"] is True


def test_mcp_check_iron_law_accepts_tests_first():
    result = _dispatch_sync("devboard_check_iron_law", {
        "tool_calls": [
            {"tool_name": "fs_write", "tool_input": {"path": "tests/test_calc.py", "content": "t"}},
            {"tool_name": "fs_write", "tool_input": {"path": "calc.py", "content": "x"}},
        ],
    })
    payload = _json_payload(result)
    assert payload["violated"] is False


def test_mcp_check_command_safety_blocks_hard():
    result = _dispatch_sync("devboard_check_command_safety", {"command": "rm -rf /"})
    payload = _json_payload(result)
    assert payload["level"] == "block"


def test_mcp_check_command_safety_warns():
    result = _dispatch_sync("devboard_check_command_safety", {"command": "git push --force"})
    payload = _json_payload(result)
    assert payload["level"] == "warn"


def test_mcp_check_command_safety_safe():
    result = _dispatch_sync("devboard_check_command_safety", {"command": "ls -la"})
    payload = _json_payload(result)
    assert payload["level"] == "safe"


def test_mcp_save_and_search_learnings(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    _dispatch_sync("devboard_save_learning", {
        "project_root": str(tmp_path),
        "name": "div_tip", "content": "Always handle ZeroDivisionError explicitly.",
        "tags": ["python", "arithmetic"],
        "category": "pattern", "confidence": 0.9,
    })

    result = _dispatch_sync("devboard_search_learnings", {
        "project_root": str(tmp_path), "tag": "python",
    })
    payload = _json_payload(result)
    assert len(payload) == 1
    assert payload[0]["name"] == "div_tip"
    assert payload[0]["confidence"] == 0.9


def test_mcp_generate_retro_empty(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    result = _dispatch_sync("devboard_generate_retro", {"project_root": str(tmp_path)})
    payload = _json_payload(result)
    assert "markdown" in payload
    assert "Retrospective" in payload["markdown"]


def test_mcp_list_runs_empty(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    result = _dispatch_sync("devboard_list_runs", {"project_root": str(tmp_path)})
    payload = _json_payload(result)
    assert payload == []


def test_mcp_unknown_tool_returns_error():
    result = _dispatch_sync("devboard_nonexistent", {})
    payload = _json_payload(result)
    assert "error" in payload


def test_mcp_error_in_handler_returns_error():
    # Missing required project_root
    result = _dispatch_sync("devboard_list_goals", {})
    payload = _json_payload(result)
    assert "error" in payload


# ══════════════════════════════════════════════════════════════════════════════
# Install script
# ══════════════════════════════════════════════════════════════════════════════

def test_install_skills_copies_all(tmp_path: Path):
    installed = install_skills(tmp_path, overwrite=True)
    names = {p.name for p in installed}
    expected = {
        "devboard-brainstorm", "devboard-gauntlet", "devboard-eng-review",
        "devboard-tdd", "devboard-cso", "devboard-dep-audit",
        "devboard-redteam", "devboard-rca",
        "devboard-approval", "devboard-retro", "devboard-replay",
    }
    assert names == expected

    # Each must have SKILL.md
    for p in installed:
        assert (p / "SKILL.md").exists()


def test_install_skills_skips_existing(tmp_path: Path):
    install_skills(tmp_path, overwrite=False)
    # Second call without overwrite returns nothing new
    installed = install_skills(tmp_path, overwrite=False)
    assert installed == []


def test_install_hooks_copies_and_makes_executable(tmp_path: Path):
    installed = install_hooks(tmp_path, overwrite=True)
    names = {p.name for p in installed}
    assert "iron-law-check.sh" in names
    assert "danger-guard.sh" in names
    for p in installed:
        assert p.stat().st_mode & 0o111  # executable


def test_emit_mcp_config_creates_file(tmp_path: Path):
    path = emit_mcp_config(tmp_path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert "mcpServers" in data
    assert "devboard" in data["mcpServers"]
    assert data["mcpServers"]["devboard"]["args"] == ["-m", "devboard.mcp_server"]


def test_emit_mcp_config_defaults_to_sys_executable(tmp_path: Path):
    """Without --python, the config should point at the currently-running Python."""
    import sys
    path = emit_mcp_config(tmp_path)
    data = json.loads(path.read_text())
    assert data["mcpServers"]["devboard"]["command"] == sys.executable


def test_emit_mcp_config_respects_explicit_python(tmp_path: Path):
    path = emit_mcp_config(tmp_path, python_bin="/custom/python")
    data = json.loads(path.read_text())
    assert data["mcpServers"]["devboard"]["command"] == "/custom/python"


def test_emit_mcp_config_preserves_existing_servers(tmp_path: Path):
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))

    emit_mcp_config(tmp_path)
    data = json.loads(path.read_text())
    assert "other" in data["mcpServers"]
    assert "devboard" in data["mcpServers"]


def test_emit_settings_hooks_registers_both(tmp_path: Path):
    path = emit_settings_hooks(tmp_path)
    data = json.loads(path.read_text())
    assert "hooks" in data
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]

    pre = data["hooks"]["PreToolUse"]
    assert any(
        any("danger-guard.sh" in h.get("command", "") for h in entry.get("hooks", []))
        for entry in pre
    )


def test_emit_settings_hooks_idempotent(tmp_path: Path):
    emit_settings_hooks(tmp_path)
    emit_settings_hooks(tmp_path)  # Second call should not duplicate
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    pre = data["hooks"]["PreToolUse"]
    # Exactly one danger-guard entry
    count = sum(
        1 for entry in pre
        for h in entry.get("hooks", [])
        if "danger-guard.sh" in h.get("command", "")
    )
    assert count == 1


def test_install_all_project_scope(tmp_path: Path):
    result = install_all(scope="project", project_root=tmp_path, overwrite=True)
    assert result["scope"] == "project"
    assert len(result["installed_skills"]) == 11
    assert len(result["installed_hooks"]) == 3  # iron-law.sh + danger-guard.sh + activity-log.py
    assert result["mcp_config"] is not None
    assert result["settings"] is not None
    assert (tmp_path / ".claude" / "skills" / "devboard-tdd" / "SKILL.md").exists()
    assert (tmp_path / ".mcp.json").exists()


def test_install_all_global_scope_no_hooks_or_mcp(tmp_path: Path, monkeypatch):
    # Redirect HOME to tmp_path so we don't pollute real ~/.claude
    monkeypatch.setenv("HOME", str(tmp_path))
    import os
    os.environ["HOME"] = str(tmp_path)
    # Also patch Path.home()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = install_all(scope="global", overwrite=True)
    assert result["scope"] == "global"
    assert len(result["installed_skills"]) == 11
    assert result["installed_hooks"] == []
    assert result["mcp_config"] is None
    assert (tmp_path / ".claude" / "skills" / "devboard-gauntlet" / "SKILL.md").exists()


def test_install_all_rejects_bad_scope():
    with pytest.raises(ValueError, match="scope must be"):
        install_all(scope="bogus")


# ══════════════════════════════════════════════════════════════════════════════
# Skill files sanity
# ══════════════════════════════════════════════════════════════════════════════

def test_all_skills_have_required_frontmatter():
    import frontmatter
    skills_dir = Path(__file__).parent.parent / "skills"
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
    assert len(skill_dirs) == 11

    for sd in skill_dirs:
        skill_md = sd / "SKILL.md"
        assert skill_md.exists(), f"{sd.name} missing SKILL.md"
        post = frontmatter.load(str(skill_md))
        assert post.metadata.get("name"), f"{sd.name} missing 'name'"
        assert post.metadata.get("description"), f"{sd.name} missing 'description'"
        assert len(post.content) > 200, f"{sd.name} body too short"


# ── devboard_save_brainstorm ──────────────────────────────────────────────────

def test_mcp_save_brainstorm_happy_path(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path),
        "title": "Brainstorm goal",
    })
    goal_id = _json_payload(add)["goal_id"]

    result = _dispatch_sync("devboard_save_brainstorm", {
        "project_root": str(tmp_path),
        "goal_id": goal_id,
        "premises": ["Users need fast search"],
        "risks": ["Over-engineering"],
        "alternatives": ["Use existing lib"],
        "existing_code_notes": "see search.py",
    })
    payload = _json_payload(result)
    assert payload.get("status") == "saved"

    bs_path = tmp_path / ".devboard" / "goals" / goal_id / "brainstorm.md"
    assert bs_path.exists()
    assert "Users need fast search" in bs_path.read_text()


def test_mcp_save_brainstorm_goal_not_found(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    result = _dispatch_sync("devboard_save_brainstorm", {
        "project_root": str(tmp_path),
        "goal_id": "g_nonexistent",
        "premises": [],
        "risks": [],
        "alternatives": [],
        "existing_code_notes": "",
    })
    payload = _json_payload(result)
    assert "error" in payload


# ── devboard_approve_plan ─────────────────────────────────────────────────────

def test_mcp_approve_plan_approved_true(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path),
        "title": "Approval goal",
    })
    goal_id = _json_payload(add)["goal_id"]

    result = _dispatch_sync("devboard_approve_plan", {
        "project_root": str(tmp_path),
        "goal_id": goal_id,
        "approved": True,
    })
    payload = _json_payload(result)
    assert payload["status"] == "approved"

    review_path = tmp_path / ".devboard" / "goals" / goal_id / "plan_review.json"
    import json as _json
    data = _json.loads(review_path.read_text())
    assert data["status"] == "approved"


def test_mcp_approve_plan_false_without_target_errors(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path),
        "title": "Approval goal 2",
    })
    goal_id = _json_payload(add)["goal_id"]

    result = _dispatch_sync("devboard_approve_plan", {
        "project_root": str(tmp_path),
        "goal_id": goal_id,
        "approved": False,
    })
    payload = _json_payload(result)
    assert "error" in payload


# ── devboard_lock_plan approval gate ─────────────────────────────────────────

_DECIDE_JSON = {
    "problem": "Build a calculator",
    "non_goals": [],
    "scope_decision": "HOLD",
    "architecture": "Single calculator.py",
    "known_failure_modes": [],
    "goal_checklist": ["add works"],
    "out_of_scope_guard": [],
    "atomic_steps": [
        {"id": "s_001", "behavior": "add(1,2)==3",
         "test_file": "tests/test_calc.py", "test_name": "test_add",
         "impl_file": "calc.py"},
    ],
    "token_ceiling": 100_000,
    "max_iterations": 3,
}


def test_mcp_lock_plan_without_approval_errors(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path),
        "title": "Gate test goal",
    })
    goal_id = _json_payload(add)["goal_id"]

    result = _dispatch_sync("devboard_lock_plan", {
        "project_root": str(tmp_path),
        "goal_id": goal_id,
        "decide_json": _DECIDE_JSON,
    })
    payload = _json_payload(result)
    assert "error" in payload
    assert "approval" in payload["error"].lower()


def test_mcp_lock_plan_with_approval_succeeds(tmp_path: Path):
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {
        "project_root": str(tmp_path),
        "title": "Gate approved goal",
    })
    goal_id = _json_payload(add)["goal_id"]

    _dispatch_sync("devboard_approve_plan", {
        "project_root": str(tmp_path),
        "goal_id": goal_id,
        "approved": True,
    })

    result = _dispatch_sync("devboard_lock_plan", {
        "project_root": str(tmp_path),
        "goal_id": goal_id,
        "decide_json": _DECIDE_JSON,
    })
    payload = _json_payload(result)
    assert payload.get("locked_hash")


# ── Task.metadata + update_task_status merge semantics ───────────────────────

def test_task_metadata_defaults_to_empty_dict():
    from devboard.models import Task
    t = Task(goal_id="g", title="t")
    assert t.metadata == {}


def _make_task_for_metadata_test(tmp_path: Path, initial_metadata: dict | None = None):
    """Helper — initialize a board with one goal + one persisted task."""
    from devboard.models import Task
    from devboard.storage.file_store import FileStore

    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync(
        "devboard_add_goal",
        {"project_root": str(tmp_path), "title": "x"},
    )
    goal_id = _json_payload(add)["goal_id"]

    store = FileStore(tmp_path)
    board = store.load_board()
    task = Task(goal_id=goal_id, title="t", metadata=dict(initial_metadata or {}))
    board.goals[0].task_ids.append(task.id)
    store.save_task(task)
    store.save_board(board)
    return store, goal_id, task.id


def test_update_task_status_absent_metadata_preserves_existing(tmp_path: Path):
    store, goal_id, task_id = _make_task_for_metadata_test(tmp_path, {"security_sensitive": True})
    _dispatch_sync(
        "devboard_update_task_status",
        {"project_root": str(tmp_path), "task_id": task_id, "status": "in_progress"},
    )
    reloaded = store.load_task(goal_id, task_id)
    assert reloaded.metadata == {"security_sensitive": True}


def test_update_task_status_sets_metadata(tmp_path: Path):
    store, goal_id, task_id = _make_task_for_metadata_test(tmp_path)
    _dispatch_sync(
        "devboard_update_task_status",
        {
            "project_root": str(tmp_path),
            "task_id": task_id,
            "status": "in_progress",
            "metadata": {"security_sensitive": True},
        },
    )
    reloaded = store.load_task(goal_id, task_id)
    assert reloaded.metadata == {"security_sensitive": True}


def test_metadata_merges_distinct_keys(tmp_path: Path):
    store, goal_id, task_id = _make_task_for_metadata_test(tmp_path, {"a": 1})
    _dispatch_sync(
        "devboard_update_task_status",
        {
            "project_root": str(tmp_path),
            "task_id": task_id,
            "status": "in_progress",
            "metadata": {"b": 2},
        },
    )
    reloaded = store.load_task(goal_id, task_id)
    assert reloaded.metadata == {"a": 1, "b": 2}


def test_metadata_overwrites_same_key(tmp_path: Path):
    store, goal_id, task_id = _make_task_for_metadata_test(tmp_path, {"a": 1})
    _dispatch_sync(
        "devboard_update_task_status",
        {
            "project_root": str(tmp_path),
            "task_id": task_id,
            "status": "in_progress",
            "metadata": {"a": 2},
        },
    )
    reloaded = store.load_task(goal_id, task_id)
    assert reloaded.metadata == {"a": 2}


def test_task_metadata_roundtrips_through_file_store(tmp_path: Path):
    from devboard.models import Task
    from devboard.storage.file_store import FileStore

    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync("devboard_add_goal", {"project_root": str(tmp_path), "title": "x"})
    goal_id = _json_payload(add)["goal_id"]

    store = FileStore(tmp_path)
    task = Task(goal_id=goal_id, title="t", metadata={"production_destined": True, "note": "x"})
    store.save_task(task)
    reloaded = store.load_task(goal_id, task.id)
    assert reloaded.metadata == {"production_destined": True, "note": "x"}
