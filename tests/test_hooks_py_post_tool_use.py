"""PostToolUse hook — captures tool-call events tagged source=user_hook.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §Data Flow. Same tool
call is also captured by MCP dispatch; event_dedup distinguishes via source.
"""

import json
from pathlib import Path

from agentboard.hooks_py import post_tool_use


def test_post_tool_use_tags_source_user_hook(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    post_tool_use.main(
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_call_seq": 1,
            "ts_bucket": 1,
        }
    )
    decisions_path = fake_home / ".agentboard" / "decisions.jsonl"
    assert decisions_path.is_file()
    lines = decisions_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry.get("source") == "user_hook"
