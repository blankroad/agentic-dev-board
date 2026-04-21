from __future__ import annotations

import subprocess
from pathlib import Path

from agentboard.tools.base import ToolDef, ToolRegistry


def _run_git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=30,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"ERROR: git {' '.join(args)} failed:\n{err or out}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: git command timed out"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def make_git_tools(cwd: Path, registry: ToolRegistry) -> None:
    def git_status() -> str:
        return _run_git(["status", "--short"], cwd)

    def git_diff(staged: bool = False) -> str:
        args = ["diff", "--stat"]
        if staged:
            args.append("--cached")
        return _run_git(args, cwd)

    def git_diff_content(path: str = "", staged: bool = False) -> str:
        args = ["diff"]
        if staged:
            args.append("--cached")
        if path:
            args += ["--", path]
        return _run_git(args, cwd)

    def git_log(n: int = 10, branch: str = "") -> str:
        args = ["log", f"-{n}", "--oneline"]
        if branch:
            args.append(branch)
        return _run_git(args, cwd)

    def git_branch_list() -> str:
        return _run_git(["branch", "-a"], cwd)

    def git_checkout(branch: str, create: bool = False) -> str:
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(branch)
        return _run_git(args, cwd)

    def git_add(path: str = ".") -> str:
        return _run_git(["add", path], cwd)

    def git_commit(message: str) -> str:
        if not message.strip():
            return "ERROR: Commit message cannot be empty"
        return _run_git(["commit", "-m", message], cwd)

    registry.register(
        ToolDef("git_status", "Show working tree status (short format).",
                {"type": "object", "properties": {}, "required": []}),
        git_status,
    )
    registry.register(
        ToolDef("git_diff", "Show diff stats. Pass staged=true for staged changes.",
                {"type": "object", "properties": {
                    "staged": {"type": "boolean", "description": "Show staged diff (default false)"},
                }, "required": []}),
        git_diff,
    )
    registry.register(
        ToolDef("git_diff_content", "Show full diff content, optionally for a specific path.",
                {"type": "object", "properties": {
                    "path": {"type": "string", "description": "File path to diff (optional)"},
                    "staged": {"type": "boolean", "description": "Show staged diff (default false)"},
                }, "required": []}),
        git_diff_content,
    )
    registry.register(
        ToolDef("git_log", "Show recent commits.",
                {"type": "object", "properties": {
                    "n": {"type": "integer", "description": "Number of commits (default 10)"},
                    "branch": {"type": "string", "description": "Branch name (optional)"},
                }, "required": []}),
        git_log,
    )
    registry.register(
        ToolDef("git_branch_list", "List all branches.",
                {"type": "object", "properties": {}, "required": []}),
        git_branch_list,
    )
    registry.register(
        ToolDef("git_checkout", "Checkout or create a branch.",
                {"type": "object", "properties": {
                    "branch": {"type": "string", "description": "Branch name"},
                    "create": {"type": "boolean", "description": "Create branch if true (default false)"},
                }, "required": ["branch"]}),
        git_checkout,
    )
    registry.register(
        ToolDef("git_add", "Stage files for commit.",
                {"type": "object", "properties": {
                    "path": {"type": "string", "description": "Path to stage (default '.')"},
                }, "required": []}),
        git_add,
    )
    registry.register(
        ToolDef("git_commit", "Create a commit with the given message. Never force-push.",
                {"type": "object", "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                }, "required": ["message"]}),
        git_commit,
    )
