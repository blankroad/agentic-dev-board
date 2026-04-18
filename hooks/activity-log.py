#!/usr/bin/env python3
"""PostToolUse hook — captures every tool invocation to .devboard/activity.jsonl
so the trial-and-error process (not just final decisions) is reviewable via
`devboard activity`.

Recorded for each call: timestamp, tool, key input fields, error flag, and a
short result preview. Large outputs are truncated.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _find_root(cwd: Path) -> Path | None:
    for d in [cwd] + list(cwd.parents):
        if (d / ".devboard").is_dir():
            return d
    return None


def _summarize(tool_name: str, tool_input: dict, tool_response: dict) -> dict:
    summary: dict = {}
    t = tool_name or ""

    if t in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        summary["path"] = tool_input.get("file_path", "") or tool_input.get("path", "")
        # quick size hint
        if isinstance(tool_response, dict):
            if "content" in tool_input:
                summary["wrote_bytes"] = len(tool_input.get("content", ""))
    elif t == "Bash":
        cmd = tool_input.get("command", "") or ""
        summary["command"] = cmd[:200]
        if isinstance(tool_response, dict):
            out = (tool_response.get("output") or tool_response.get("stdout") or "")
            err = (tool_response.get("stderr") or "")
            summary["exit_code"] = tool_response.get("exit_code", tool_response.get("code"))
            # capture pytest result lines
            combined = (out + "\n" + err)[-400:]
            # find "N passed" / "N failed"
            for line in combined.splitlines()[-4:]:
                if "passed" in line or "failed" in line or "error" in line.lower():
                    summary["result_tail"] = line.strip()[:160]
                    break
    elif t == "Read":
        summary["path"] = tool_input.get("file_path", "") or tool_input.get("path", "")
    elif t.startswith("mcp__") or "devboard" in t.lower():
        summary["mcp_tool"] = t
        # MCP tools often return JSON — try to capture warnings
        if isinstance(tool_response, dict):
            content = tool_response.get("content")
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and "text" in first:
                    try:
                        parsed = json.loads(first["text"])
                        if isinstance(parsed, dict):
                            if parsed.get("warnings"):
                                summary["warnings"] = parsed["warnings"]
                            if "event" in parsed:
                                summary["event"] = parsed["event"]
                            if "error" in parsed:
                                summary["mcp_error"] = parsed["error"]
                    except Exception:
                        pass
    return summary


def _detect_error(tool_response: dict) -> bool:
    if not isinstance(tool_response, dict):
        return False
    if tool_response.get("is_error"):
        return True
    exit_code = tool_response.get("exit_code", tool_response.get("code"))
    if isinstance(exit_code, int) and exit_code != 0:
        return True
    # Tool-specific error patterns
    for key in ("output", "stdout", "stderr"):
        v = tool_response.get(key, "")
        if isinstance(v, str) and ("Traceback" in v or " error " in v.lower() or "FAILED" in v):
            return True
    return False


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}
    tool_response = data.get("tool_response", {}) or {}
    session_id = data.get("session_id", "")

    # Find .devboard/ root
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    root = _find_root(cwd)
    if root is None:
        sys.exit(0)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "tool": tool_name,
        "is_error": _detect_error(tool_response),
        **_summarize(tool_name, tool_input, tool_response),
    }

    log_path = root / ".devboard" / "activity.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass  # never block the tool


if __name__ == "__main__":
    main()
