"""Goal #2 — devboard_lock_plan writes a ## Metadata section to plan.md.

Tests for the Metadata block written at lock time (git identity + branch +
ISO locked_at + locked_hash). Covers happy path + git-config-absent fallback
+ branch detection + idempotency on rerun.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────


def _dispatch_sync(tool_name: str, args: dict):
    from devboard.mcp_server import call_tool
    return asyncio.run(call_tool(tool_name, args))


def _json_payload(result):
    return json.loads(result[0].text)


def _decide_json() -> dict:
    return {
        "problem": "Build feature X",
        "non_goals": [],
        "scope_decision": "HOLD",
        "architecture": "single module",
        "known_failure_modes": [],
        "goal_checklist": ["does X"],
        "out_of_scope_guard": [],
        "atomic_steps": [
            {
                "id": "s_001",
                "behavior": "X works",
                "test_file": "tests/test_x.py",
                "test_name": "test_x",
                "impl_file": "x.py",
            },
        ],
        "token_ceiling": 100_000,
        "max_iterations": 3,
    }


def _init_and_lock(project_root: Path) -> tuple[str, Path]:
    """Run the usual init→add_goal→approve→lock_plan dance under
    ``project_root`` and return (goal_id, plan_md_path)."""
    _dispatch_sync("devboard_init", {"project_root": str(project_root)})
    add = _dispatch_sync(
        "devboard_add_goal",
        {"project_root": str(project_root), "title": "t", "description": "d"},
    )
    goal_id = _json_payload(add)["goal_id"]
    _dispatch_sync(
        "devboard_approve_plan",
        {"project_root": str(project_root), "goal_id": goal_id, "approved": True},
    )
    result = _dispatch_sync(
        "devboard_lock_plan",
        {
            "project_root": str(project_root),
            "goal_id": goal_id,
            "decide_json": _decide_json(),
        },
    )
    plan_path = Path(_json_payload(result)["plan_path"])
    return goal_id, plan_path


def _make_git_repo(path: Path, *, name: str | None, email: str | None,
                   branch: str = "main") -> None:
    """Initialize a fresh git repo at ``path`` with local user.name/email
    set (or unset) as requested. Uses `git init -b <branch>` so we control
    the current ref."""
    subprocess.run(
        ["git", "init", "-b", branch],
        cwd=path,
        capture_output=True,
        check=True,
        timeout=5,
    )
    if name is not None:
        subprocess.run(
            ["git", "config", "user.name", name],
            cwd=path, capture_output=True, check=True, timeout=5,
        )
    if email is not None:
        subprocess.run(
            ["git", "config", "user.email", email],
            cwd=path, capture_output=True, check=True, timeout=5,
        )


# ── tests ─────────────────────────────────────────────────────────────────────


def test_lock_plan_writes_metadata_section(tmp_path: Path) -> None:
    """Happy path: after lock_plan, plan.md contains a ## Metadata block with
    Goal ID / Locked at / Locked hash fields."""
    goal_id, plan_path = _init_and_lock(tmp_path)
    text = plan_path.read_text()
    assert "## Metadata" in text, "Metadata heading missing from plan.md"
    assert f"Goal ID: {goal_id}" in text
    assert "Locked at:" in text
    assert "Locked hash:" in text


def test_lock_plan_metadata_owner_from_git_config(tmp_path: Path) -> None:
    """When git user.name + user.email are set on the project root, Owner
    reads ``Name <email>``.

    # guards: edge-case-red-rule
    """
    _make_git_repo(tmp_path, name="Alice Example", email="alice@example.com")
    _, plan_path = _init_and_lock(tmp_path)
    text = plan_path.read_text()
    # Metadata section must contain a readable Owner line referencing both
    # the configured name and email.
    assert "Owner: Alice Example <alice@example.com>" in text, (
        f"Owner line missing or malformed. plan.md contents:\n{text}"
    )


def test_lock_plan_metadata_owner_unknown_fallback(tmp_path: Path) -> None:
    """When git config lacks user.name / user.email (e.g. throwaway CI
    worker), Owner falls back to the literal string 'unknown' — the helper
    must not raise.

    # guards: edge-case-red-rule
    """
    # No git repo at all in tmp_path → `git config user.name` returns
    # non-zero, stdout empty. Helper must catch and fall back.
    _, plan_path = _init_and_lock(tmp_path)
    text = plan_path.read_text()
    # Extract Owner line from the Metadata section.
    owner_lines = [ln for ln in text.splitlines() if ln.startswith("- Owner:")]
    assert owner_lines, f"Owner line missing. plan.md:\n{text}"
    assert owner_lines[0].strip() == "- Owner: unknown", (
        f"expected 'unknown' fallback, got: {owner_lines[0]!r}"
    )


def test_lock_plan_metadata_branch_detected(tmp_path: Path) -> None:
    """Branch line reflects the current git HEAD short ref."""
    _make_git_repo(
        tmp_path, name="Bob", email="bob@example.com", branch="feature-xyz",
    )
    _, plan_path = _init_and_lock(tmp_path)
    text = plan_path.read_text()
    branch_lines = [ln for ln in text.splitlines() if ln.startswith("- Branch:")]
    assert branch_lines, f"Branch line missing. plan.md:\n{text}"
    assert branch_lines[0].strip() == "- Branch: feature-xyz", (
        f"expected 'feature-xyz', got: {branch_lines[0]!r}"
    )


def test_lock_plan_is_idempotent_on_rerun(tmp_path: Path) -> None:
    """Calling lock_plan twice must result in a single Metadata block, not
    two stacked ones (leverages upsert_plan_section's idempotency).

    # guards: edge-case-red-rule
    """
    goal_id, plan_path = _init_and_lock(tmp_path)
    # Re-run lock_plan with the same inputs. Need to re-approve because
    # save_locked_plan clears the approval review file? — check first run
    # output to be safe; we just drive the same dispatch twice.
    _dispatch_sync(
        "devboard_approve_plan",
        {"project_root": str(tmp_path), "goal_id": goal_id, "approved": True},
    )
    _dispatch_sync(
        "devboard_lock_plan",
        {
            "project_root": str(tmp_path),
            "goal_id": goal_id,
            "decide_json": _decide_json(),
        },
    )
    text = plan_path.read_text()
    assert text.count("## Metadata") == 1, (
        f"Metadata section duplicated on rerun:\n{text}"
    )
