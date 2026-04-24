"""Goal checklist #4 — hook + MCP capture of the same tool call dedups to 1.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 goal_checklist item 4.

Even though `source` distinguishes user/project hook content (FM6), at the
decisions.jsonl WRITE boundary the two captures of a single physical tool
call must collapse to a single entry — retro/replay readers treat the event
as atomic.
"""

from pathlib import Path

from agentboard.hooks_py import post_tool_use
from agentboard.storage.global_store import GlobalStore


def test_hook_and_mcp_dual_capture_yields_one_entry(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    payload = {
        "session_id": "s-dual",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_call_seq": 1,
        "ts_bucket": 1,
    }
    # Hook capture (source=user_hook).
    post_tool_use.main(payload)
    # Simulated MCP capture of the same physical event (source=mcp).
    import json

    GlobalStore().write_decision(
        {
            "kind": "tool_use",
            "source": "mcp",
            "session_id": payload["session_id"],
            "tool": payload["tool_name"],
            "args": payload["tool_input"],
        },
        source="mcp",
        session_id=payload["session_id"],
        tool_call_seq=payload["tool_call_seq"],
        tool_name=payload["tool_name"],
        args_json=json.dumps(payload["tool_input"], sort_keys=True),
        ts_bucket=payload["ts_bucket"],
    )
    decisions_path = fake_home / ".agentboard" / "decisions.jsonl"
    lines = decisions_path.read_text().splitlines()
    assert len(lines) == 1
