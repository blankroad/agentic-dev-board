from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

import pytest

from devboard.models import DecisionEntry, LockedPlan
from devboard.gauntlet.lock import build_locked_plan
from devboard.orchestrator.approval import (
    POLICIES,
    apply_squash_policy,
    build_pr_body,
    get_diff_stats,
)
from devboard.orchestrator.push import push_and_create_pr, PushResult


# ── Helpers ──────────────────────────────────────────────────────────────────

def _plan() -> LockedPlan:
    return build_locked_plan("g_001", {
        "problem": "Build a calculator with add/sub/mul/div",
        "non_goals": ["GUI", "scientific ops"],
        "scope_decision": "HOLD",
        "architecture": "Single calculator.py with 4 pure functions",
        "known_failure_modes": ["div-by-zero"],
        "goal_checklist": ["add() works", "div() raises ZeroDivisionError", "pytest passes"],
        "out_of_scope_guard": ["src/payments/"],
        "token_ceiling": 100_000,
        "max_iterations": 5,
    })


def _decisions() -> list[DecisionEntry]:
    return [
        DecisionEntry(iter=1, phase="review", reasoning="Missing div-by-zero test", next_strategy="", verdict_source="RETRY"),
        DecisionEntry(iter=1, phase="reflect", reasoning="Test not added", next_strategy="Add explicit ZeroDivisionError test"),
        DecisionEntry(iter=2, phase="review", reasoning="All checks pass", next_strategy="", verdict_source="PASS"),
    ]


# ── build_pr_body ─────────────────────────────────────────────────────────────

def test_pr_body_contains_problem():
    body = build_pr_body(_plan(), _decisions(), iterations_completed=2)
    assert "Build a calculator" in body


def test_pr_body_contains_checklist():
    body = build_pr_body(_plan(), _decisions(), iterations_completed=2)
    assert "add() works" in body
    assert "pytest passes" in body


def test_pr_body_contains_iteration_stats():
    body = build_pr_body(_plan(), _decisions(), iterations_completed=2)
    assert "2 iteration" in body


def test_pr_body_contains_key_decisions():
    body = build_pr_body(_plan(), _decisions(), iterations_completed=2)
    assert "ZeroDivisionError" in body


def test_pr_body_with_diff_stats():
    body = build_pr_body(_plan(), _decisions(), iterations_completed=2, diff_stats="calculator.py | 20 ++")
    assert "calculator.py" in body


def test_pr_body_no_retries_message():
    body = build_pr_body(_plan(), [], iterations_completed=1)
    assert "no retries" in body or "first attempt" in body


# ── POLICIES dict ─────────────────────────────────────────────────────────────

def test_policies_mapping():
    assert POLICIES["1"] == "squash"
    assert POLICIES["2"] == "semantic"
    assert POLICIES["3"] == "preserve"
    assert POLICIES["4"] == "interactive"


# ── apply_squash_policy ───────────────────────────────────────────────────────

def test_apply_semantic_policy_is_noop(tmp_path: Path):
    result = apply_squash_policy(tmp_path, "branch", "main", "semantic", "msg")
    assert result is True


def test_apply_preserve_policy_is_noop(tmp_path: Path):
    result = apply_squash_policy(tmp_path, "branch", "main", "preserve", "msg")
    assert result is True


def test_apply_squash_policy_calls_git(tmp_path: Path):
    with (
        patch("devboard.orchestrator.approval.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = apply_squash_policy(tmp_path, "feat/x", "main", "squash", "squash commit")
    assert result is True
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("reset" in c for c in calls)
    assert any("commit" in c for c in calls)


# ── get_diff_stats ────────────────────────────────────────────────────────────

def test_get_diff_stats_graceful_on_error(tmp_path: Path):
    # tmp_path is not a git repo — should return "" gracefully
    result = get_diff_stats(tmp_path)
    assert isinstance(result, str)


# ── push_and_create_pr ────────────────────────────────────────────────────────

def test_push_and_pr_success(tmp_path: Path):
    with (
        patch("devboard.orchestrator.push.git_push", return_value=True),
        patch("devboard.orchestrator.push.gh_pr_create", return_value="https://github.com/org/repo/pull/42"),
    ):
        result = push_and_create_pr(tmp_path, "feat/x", "My PR", "body")

    assert result.success
    assert result.pr_url == "https://github.com/org/repo/pull/42"


def test_push_and_pr_push_fails(tmp_path: Path):
    with patch("devboard.orchestrator.push.git_push", return_value=False):
        result = push_and_create_pr(tmp_path, "feat/x", "My PR", "body")

    assert not result.success
    assert "git push failed" in result.error


def test_push_and_pr_gh_fails(tmp_path: Path):
    with (
        patch("devboard.orchestrator.push.git_push", return_value=True),
        patch("devboard.orchestrator.push.gh_pr_create", return_value=""),
    ):
        result = push_and_create_pr(tmp_path, "feat/x", "My PR", "body")

    assert not result.success
    assert "gh pr create failed" in result.error
