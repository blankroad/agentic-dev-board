"""Tests for check_iron_law — Claude Code tool name mapping."""
from __future__ import annotations

import pytest

from agentboard.agents.iron_law import check_iron_law
from agentboard.tools.base import ToolCall


def _tc(tool_name: str, path: str) -> ToolCall:
    return ToolCall(tool_name=tool_name, tool_input={"file_path": path}, result="ok")


# ── Claude Code tool names must be detected ───────────────────────────────────

def test_write_to_impl_without_test_is_violation():
    """Claude Code 'Write' to production file with no prior test → violated."""
    calls = [_tc("Write", "src/agentboard/foo.py")]
    verdict = check_iron_law(calls)
    assert verdict.violated is True
    assert "src/agentboard/foo.py" in verdict.impl_writes


def test_edit_to_impl_without_test_is_violation():
    """Claude Code 'Edit' to production file with no prior test → violated."""
    calls = [_tc("Edit", "src/agentboard/bar.py")]
    verdict = check_iron_law(calls)
    assert verdict.violated is True


def test_write_test_then_write_impl_is_ok():
    """Test file written before impl → not violated."""
    calls = [
        _tc("Write", "tests/test_foo.py"),
        _tc("Write", "src/agentboard/foo.py"),
    ]
    verdict = check_iron_law(calls)
    assert verdict.violated is False
    assert "tests/test_foo.py" in verdict.test_writes


def test_write_impl_then_test_is_violation():
    """Impl written before test (wrong order) → violated."""
    calls = [
        _tc("Write", "src/agentboard/foo.py"),
        _tc("Write", "tests/test_foo.py"),
    ]
    verdict = check_iron_law(calls)
    assert verdict.violated is True


def test_only_test_writes_not_violated():
    """Only test file writes → not violated."""
    calls = [_tc("Write", "tests/test_foo.py")]
    verdict = check_iron_law(calls)
    assert verdict.violated is False


def test_empty_calls_not_violated():
    verdict = check_iron_law([])
    assert verdict.violated is False


# ── Legacy "fs_write" still works ────────────────────────────────────────────

def test_legacy_fs_write_still_detected():
    """Legacy 'fs_write' tool_name (LangGraph path) still triggers violation."""
    calls = [ToolCall(tool_name="fs_write", tool_input={"path": "src/legacy.py"}, result="ok")]
    verdict = check_iron_law(calls)
    assert verdict.violated is True
