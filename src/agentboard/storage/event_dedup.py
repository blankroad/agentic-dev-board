"""Track event_id registry across hook/MCP dual-capture streams.

event_id formula (FM3/FM6 fix): SHA256 of
  f"{source}|{session_id}|{tool_call_seq}|{tool_name}|{args_json}|{ts_bucket}"

Original arch.md line 94 formula omitted `source` and `tool_call_seq`; FM3 and FM6
demonstrated that omission lets user-scope + project-scope hook writes collide
with MCP writes, and retries collide with legitimate duplicates. Both fields
are load-bearing.
"""

import hashlib


def compute_event_id(
    source: str,
    session_id: str,
    tool_call_seq: int,
    tool_name: str,
    args_json: str,
    ts_bucket: int,
) -> str:
    key = f"{source}|{session_id}|{tool_call_seq}|{tool_name}|{args_json}|{ts_bucket}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class EventDedup:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_duplicate(
        self,
        source: str,
        session_id: str,
        tool_call_seq: int,
        tool_name: str,
        args_json: str,
        ts_bucket: int,
    ) -> bool:
        eid = compute_event_id(
            source, session_id, tool_call_seq, tool_name, args_json, ts_bucket
        )
        if eid in self._seen:
            return True
        self._seen.add(eid)
        return False
