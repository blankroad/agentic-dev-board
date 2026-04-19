"""Tests for the devboard_log_parallel_review MCP tool."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path


def _dispatch_sync(tool_name: str, args: dict):
    from devboard.mcp_server import call_tool

    return asyncio.run(call_tool(tool_name, args))


def _payload(result):
    return json.loads(result[0].text)


REQUIRED_METADATA_FIELDS = {
    "parallel_duration_s",
    "cso_duration_s",
    "redteam_duration_s",
    "cso_verdict",
    "redteam_verdict",
    "overall",
    "overlap_count",
}


def _setup_goal(tmp_path: Path) -> tuple[str, str]:
    _dispatch_sync("devboard_init", {"project_root": str(tmp_path)})
    add = _dispatch_sync(
        "devboard_add_goal",
        {"project_root": str(tmp_path), "title": "parallel-review test goal"},
    )
    goal_id = _payload(add)["goal_id"]
    start = _dispatch_sync(
        "devboard_start_task", {"project_root": str(tmp_path), "goal_id": goal_id}
    )
    task_id = _payload(start)["task_id"]
    return goal_id, task_id


def test_log_parallel_review_writes_entry_with_metadata(tmp_path: Path) -> None:
    """Writes a phase='parallel_review' entry with all 7 required metadata fields + korean body roundtrip."""
    _, task_id = _setup_goal(tmp_path)
    args = {
        "project_root": str(tmp_path),
        "task_id": task_id,
        "iter": 2,
        "cso_verdict": "SECURE",
        "redteam_verdict": "SURVIVED",
        "overall": "CLEAN",
        "parallel_duration_s": 3.5,
        "cso_duration_s": 3.1,
        "redteam_duration_s": 3.2,
        "overlap_count": 0,
        "reasoning": "한글 요약 — 양쪽 verdict 모두 CLEAN",
    }
    result = _dispatch_sync("devboard_log_parallel_review", args)
    payload = _payload(result)
    assert payload["status"] == "logged"
    assert payload["phase"] == "parallel_review"

    # Verify the entry actually lands in decisions.jsonl with all required metadata.
    load = _dispatch_sync(
        "devboard_load_decisions", {"project_root": str(tmp_path), "task_id": task_id}
    )
    entries = json.loads(load[0].text)
    parallel_entries = [e for e in entries if e.get("phase") == "parallel_review"]
    assert len(parallel_entries) == 1
    entry = parallel_entries[0]
    # Metadata must be accessible (either nested under 'metadata' or top-level — either is fine)
    flat = {**entry, **entry.get("metadata", {})}
    for field in REQUIRED_METADATA_FIELDS:
        assert field in flat, f"missing required metadata field: {field}"
    # Korean roundtrip intact (guards against json encoding issues)
    assert "한글" in (entry.get("reasoning", "") + json.dumps(entry, ensure_ascii=False))


def _valid_args(tmp_path: Path, task_id: str) -> dict:
    return {
        "project_root": str(tmp_path),
        "task_id": task_id,
        "iter": 2,
        "cso_verdict": "SECURE",
        "redteam_verdict": "SURVIVED",
        "overall": "CLEAN",
        "parallel_duration_s": 3.5,
        "cso_duration_s": 3.1,
        "redteam_duration_s": 3.2,
        "overlap_count": 0,
    }


def test_log_parallel_review_rejects_none_value(tmp_path: Path) -> None:
    # guards: mcp-required-field-check-must-reject-none
    """None for a required numeric field must produce status='error', not pass through."""
    _, task_id = _setup_goal(tmp_path)
    args = _valid_args(tmp_path, task_id)
    args["parallel_duration_s"] = None
    result = _dispatch_sync("devboard_log_parallel_review", args)
    payload = _payload(result)
    assert payload.get("status") == "error"
    assert "parallel_duration_s" in (payload.get("message") or "")


def test_log_parallel_review_rejects_string_for_numeric(tmp_path: Path) -> None:
    # guards: mcp-required-field-check-must-reject-none
    """A string value for a required numeric field must be rejected."""
    _, task_id = _setup_goal(tmp_path)
    args = _valid_args(tmp_path, task_id)
    args["parallel_duration_s"] = "fast"
    result = _dispatch_sync("devboard_log_parallel_review", args)
    payload = _payload(result)
    assert payload.get("status") == "error"
    assert "parallel_duration_s" in (payload.get("message") or "")


def test_log_parallel_review_rejects_bool_for_numeric(tmp_path: Path) -> None:
    # guards: mcp-required-field-check-must-reject-none
    """Python bool is int subclass — must be explicitly rejected for numeric duration fields."""
    _, task_id = _setup_goal(tmp_path)
    args = _valid_args(tmp_path, task_id)
    args["parallel_duration_s"] = True  # bool leaks through naive isinstance(x, (int, float))
    result = _dispatch_sync("devboard_log_parallel_review", args)
    payload = _payload(result)
    assert payload.get("status") == "error"
    assert "parallel_duration_s" in (payload.get("message") or "")


def test_log_parallel_review_rejects_missing_required_field(tmp_path: Path) -> None:
    """Omitting parallel_duration_s must be rejected with an error payload (status != 'logged')."""
    _, task_id = _setup_goal(tmp_path)
    args = {
        "project_root": str(tmp_path),
        "task_id": task_id,
        "iter": 2,
        "cso_verdict": "SECURE",
        "redteam_verdict": "SURVIVED",
        "overall": "CLEAN",
        # parallel_duration_s intentionally OMITTED
        "cso_duration_s": 3.1,
        "redteam_duration_s": 3.2,
        "overlap_count": 0,
    }
    result = _dispatch_sync("devboard_log_parallel_review", args)
    payload = _payload(result)
    assert payload.get("status") == "error"
    assert "parallel_duration_s" in (payload.get("message") or payload.get("reason") or "")
