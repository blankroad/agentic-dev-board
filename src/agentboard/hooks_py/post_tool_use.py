"""PostToolUse hook — captures tool call events into the global decisions log.

Event record is tagged ``source=user_hook`` so event_dedup can distinguish it
from the MCP-side capture of the same call (FM3/FM6).
"""

import json

from agentboard.storage.global_store import GlobalStore


def main(payload: dict) -> None:
    session_id = payload.get("session_id", "unknown")
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    args_json = json.dumps(tool_input, sort_keys=True)
    tool_call_seq = int(payload.get("tool_call_seq", 0))
    ts_bucket = int(payload.get("ts_bucket", 0))
    GlobalStore().write_decision(
        {
            "kind": "tool_use",
            "source": "user_hook",
            "session_id": session_id,
            "tool": tool_name,
            "args": tool_input,
        },
        source="user_hook",
        session_id=session_id,
        tool_call_seq=tool_call_seq,
        tool_name=tool_name,
        args_json=args_json,
        ts_bucket=ts_bucket,
    )
