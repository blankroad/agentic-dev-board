from __future__ import annotations

import subprocess
from pathlib import Path

from devboard.tools.base import ToolDef, ToolRegistry
from devboard.tools.careful import check_command

DEFAULT_ALLOWLIST = [
    "python", "python3", "pytest", "pip", "uv",
    "ls", "cat", "echo", "mkdir", "cp", "mv", "touch",
    "grep", "find", "head", "tail", "wc", "sort",
    "git", "gh",
]

_BLOCKED_PATTERNS = ["rm -rf /", ":(){ :|:& };:", "> /dev/sda"]


def _is_allowed(cmd: str, allowlist: list[str]) -> bool:
    first_word = cmd.strip().split()[0].split("/")[-1] if cmd.strip() else ""
    return first_word in allowlist


def _is_dangerous(cmd: str) -> bool:
    return any(p in cmd for p in _BLOCKED_PATTERNS)


def make_shell_tool(
    cwd: Path,
    registry: ToolRegistry,
    allowlist: list[str] | None = None,
    timeout: int = 60,
    careful: bool = True,
    strict_careful: bool = False,
) -> None:
    """Make a shell tool.

    careful: When True, DangerGuard (tools/careful.py) inspects every command.
             Hard-blocked patterns (rm -rf /, fork bombs) always rejected.
             Warn-level patterns (rm -rf, force push, DROP TABLE) rejected if strict_careful=True.
    """
    effective_allowlist = allowlist if allowlist is not None else DEFAULT_ALLOWLIST

    def shell(command: str) -> str:
        if _is_dangerous(command):
            return "ERROR: Command blocked (dangerous pattern detected)"

        if careful:
            verdict = check_command(command)
            if verdict.level == "block":
                return f"ERROR: DangerGuard blocked: {verdict.reason}"
            if verdict.level == "warn" and strict_careful:
                return f"ERROR: DangerGuard (strict): {verdict.reason}. Use --careful off or strict=false to override."

        if not _is_allowed(command, effective_allowlist):
            first = command.strip().split()[0] if command.strip() else ""
            return f"ERROR: Command '{first}' is not in the shell allowlist"
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=timeout,
            )
            out = result.stdout
            err = result.stderr
            parts = []
            if out:
                parts.append(out)
            if err:
                parts.append(f"[stderr]\n{err}")
            parts.append(f"[exit_code: {result.returncode}]")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"ERROR: Command timed out after {timeout}s"
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"

    registry.register(
        ToolDef(
            name="shell",
            description="Execute a shell command in the project directory. Only allowlisted commands are permitted.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
            },
        ),
        shell,
    )
