from __future__ import annotations

from pathlib import Path

import pytest

from agentboard.tools.base import ToolDef, ToolRegistry
from agentboard.tools.fs import make_fs_tools
from agentboard.tools.shell import make_shell_tool, _is_allowed, _is_dangerous


# ── ToolRegistry ─────────────────────────────────────────────────────────────

def test_registry_execute_unknown():
    reg = ToolRegistry()
    result = reg.execute("no_such_tool", {})
    assert result.startswith("ERROR:")


def test_registry_execute_known():
    reg = ToolRegistry()

    def add(a: int, b: int) -> str:
        return str(a + b)

    reg.register(
        ToolDef("add", "add two numbers", {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        }),
        add,
    )
    assert reg.execute("add", {"a": 3, "b": 4}) == "7"


def test_registry_definitions():
    reg = ToolRegistry()
    reg.register(ToolDef("foo", "desc", {"type": "object"}), lambda: "ok")
    defs = reg.definitions()
    assert len(defs) == 1
    assert defs[0]["name"] == "foo"
    assert "input_schema" in defs[0]


# ── FSTools ───────────────────────────────────────────────────────────────────

@pytest.fixture
def fs_registry(tmp_path: Path):
    reg = ToolRegistry()
    make_fs_tools(tmp_path, reg)
    return reg, tmp_path


def test_fs_write_and_read(fs_registry):
    reg, root = fs_registry
    result = reg.execute("fs_write", {"path": "hello.txt", "content": "world"})
    assert "Written" in result
    assert (root / "hello.txt").read_text() == "world"

    content = reg.execute("fs_read", {"path": "hello.txt"})
    assert content == "world"


def test_fs_read_missing(fs_registry):
    reg, _ = fs_registry
    result = reg.execute("fs_read", {"path": "nonexistent.txt"})
    assert result.startswith("ERROR:")


def test_fs_write_creates_subdirs(fs_registry):
    reg, root = fs_registry
    reg.execute("fs_write", {"path": "a/b/c.py", "content": "x = 1"})
    assert (root / "a" / "b" / "c.py").exists()


def test_fs_list(fs_registry):
    reg, root = fs_registry
    (root / "dir_a").mkdir()
    (root / "file.txt").write_text("x")
    result = reg.execute("fs_list", {})
    assert "dir_a/" in result
    assert "file.txt" in result


def test_fs_path_escape_blocked(fs_registry):
    reg, _ = fs_registry
    result = reg.execute("fs_read", {"path": "../../etc/passwd"})
    assert result.startswith("ERROR:")


def test_fs_write_path_escape_blocked(fs_registry):
    reg, _ = fs_registry
    result = reg.execute("fs_write", {"path": "../../evil.txt", "content": "bad"})
    assert result.startswith("ERROR:")


# ── ShellTool ─────────────────────────────────────────────────────────────────

def test_is_allowed():
    allowlist = ["python", "pytest", "echo"]
    assert _is_allowed("echo hello", allowlist)
    assert _is_allowed("python script.py", allowlist)
    assert not _is_allowed("rm -rf /", allowlist)


def test_is_dangerous():
    assert _is_dangerous("rm -rf /")
    assert not _is_dangerous("echo hello")


def test_shell_allowlisted(tmp_path: Path):
    reg = ToolRegistry()
    make_shell_tool(tmp_path, reg, allowlist=["echo"])
    result = reg.execute("shell", {"command": "echo hello"})
    assert "hello" in result
    assert "[exit_code: 0]" in result


def test_shell_blocked(tmp_path: Path):
    reg = ToolRegistry()
    make_shell_tool(tmp_path, reg, allowlist=["echo"])
    result = reg.execute("shell", {"command": "rm -f something"})
    assert result.startswith("ERROR:")


def test_shell_exit_code_nonzero(tmp_path: Path):
    reg = ToolRegistry()
    make_shell_tool(tmp_path, reg, allowlist=["python"])
    result = reg.execute("shell", {"command": "python -c \"import sys; sys.exit(1)\""})
    assert "[exit_code: 1]" in result
