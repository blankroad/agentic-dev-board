from __future__ import annotations

from pathlib import Path

from agentboard.tui.tail_worker import FileTail


def test_worker_emits_appended_lines_in_order(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text('{"n": 1}\n{"n": 2}\n')
    tail = FileTail(p)

    first = tail.read_new_lines()
    assert first == ['{"n": 1}', '{"n": 2}']

    p.write_text(p.read_text() + '{"n": 3}\n{"n": 4}\n')
    second = tail.read_new_lines()
    assert second == ['{"n": 3}', '{"n": 4}']

    assert tail.read_new_lines() == []


def test_worker_buffers_partial_line_until_newline(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text('{"n": 1}\n')
    tail = FileTail(p)

    assert tail.read_new_lines() == ['{"n": 1}']

    # Half-written line: no newline yet
    p.write_text(p.read_text() + '{"n": 2')
    assert tail.read_new_lines() == []

    # Completing the line
    p.write_text(p.read_text() + '}\n')
    assert tail.read_new_lines() == ['{"n": 2}']


def test_worker_skips_invalid_utf8_completed_line(tmp_path: Path) -> None:
    """Red-team round 2 — Attack 3: a completed line with invalid UTF-8
    bytes must not kill the worker. Skip the line, keep polling."""
    p = tmp_path / "events.jsonl"
    p.write_bytes(b'\xff\xfe\xfd garbage\n{"ok": 1}\n')
    tail = FileTail(p)
    lines = tail.read_new_lines()
    # Expect the valid line present; invalid one silently dropped
    assert '{"ok": 1}' in lines
    # Must not raise; worker survives to next poll
    assert tail.read_new_lines() == []


def test_worker_buffers_partial_multibyte_char(tmp_path: Path) -> None:
    """Red-team A3: when a 3-byte UTF-8 char ('한' = E\\xED\\x95\\x9C) is
    split across polls, the worker must not crash with UnicodeDecodeError.
    It buffers bytes until the char is complete + a newline arrives."""
    p = tmp_path / "events.jsonl"
    p.write_bytes(b'{"a": 1}\n')
    tail = FileTail(p)
    assert tail.read_new_lines() == ['{"a": 1}']

    # Write prefix + 2 of 3 bytes of '한'
    with open(p, "ab") as fh:
        fh.write(b'{"k": "')
        fh.write(b"\xed\x95")  # incomplete multi-byte
        fh.flush()
    # Must NOT raise, returns no complete lines yet
    assert tail.read_new_lines() == []

    # Finish the char and the line
    with open(p, "ab") as fh:
        fh.write(b'\x9c"}\n')
    assert tail.read_new_lines() == ['{"k": "한"}']
