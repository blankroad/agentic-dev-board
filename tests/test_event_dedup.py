"""Dedup across hook/MCP dual-capture streams.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 — Cross-Project Memory.
Addresses FM3 (retry vs dual-capture) + FM6 (same seq, different source).
"""

from agentboard.storage import event_dedup


def test_compute_event_id_changes_with_source() -> None:
    # guards FM6: source must distinguish hashes for same-seq-different-source writes.
    h_hook = event_dedup.compute_event_id(
        source="hook",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    h_mcp = event_dedup.compute_event_id(
        source="mcp",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    assert h_hook != h_mcp


def test_compute_event_id_changes_with_tool_call_seq() -> None:
    # guards FM3: tool_call_seq must distinguish hashes across retries.
    h1 = event_dedup.compute_event_id(
        source="hook",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    h2 = event_dedup.compute_event_id(
        source="hook",
        session_id="s1",
        tool_call_seq=2,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    assert h1 != h2


def test_is_duplicate_returns_true_on_second_same_write() -> None:
    d = event_dedup.EventDedup()
    first = d.is_duplicate(
        source="hook",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    second = d.is_duplicate(
        source="hook",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    assert first is False
    assert second is True


def test_is_duplicate_returns_false_for_different_source() -> None:
    # FM6: user-scope hook + project-scope hook on same (session, seq) must
    # NOT be dedup'd away — different sources may carry different content.
    d = event_dedup.EventDedup()
    d.is_duplicate(
        source="hook",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    result = d.is_duplicate(
        source="mcp",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    assert result is False
