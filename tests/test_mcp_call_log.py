"""MCP call log telemetry tests (p_009, p_010)."""
from __future__ import annotations

import json
from pathlib import Path


async def test_mcp_calls_logged_per_dispatch(tmp_path: Path) -> None:
    """p_009: every call_tool dispatch appends a jsonl entry to
    .agentboard/mcp_calls.jsonl with {tool, ts, duration_ms, bytes_returned}.
    """
    from agentboard.mcp_server import call_tool

    # Seed a simple pile so get_session succeeds (reuses prior tests)
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter
    from agentboard.storage.pile_session import SessionWriter

    store = FileStore(tmp_path)
    rid = "run_log"
    store.write_iter_artifact(rid, 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    ChapterWriter(store).regen_labor(rid)
    SessionWriter(store).regen(
        rid, goal_title="x", current_phase="tdd_red", total_steps=1, last_verdict="R",
    )

    # 3 MCP calls
    await call_tool("agentboard_get_session", {"project_root": str(tmp_path), "rid": rid})
    await call_tool("agentboard_get_chapter", {"project_root": str(tmp_path), "rid": rid, "chapter": "labor"})
    await call_tool("agentboard_get_session", {"project_root": str(tmp_path), "rid": rid})

    log_path = tmp_path / ".agentboard" / "mcp_calls.jsonl"
    assert log_path.exists(), "mcp_calls.jsonl not created"
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 3, f"expected 3 log entries, got {len(lines)}"
    for ln in lines:
        entry = json.loads(ln)
        assert "tool" in entry
        assert "ts" in entry
        assert "duration_ms" in entry
        assert "bytes_returned" in entry
        assert entry["tool"] in (
            "agentboard_get_session", "agentboard_get_session",
            "agentboard_get_chapter", "agentboard_get_chapter",
        )


async def test_telemetry_failure_swallowed(tmp_path: Path, monkeypatch) -> None:
    """p_010: telemetry append failure must NOT break primary dispatch.
    Simulate failure by making the log path unwritable, then call a
    tool and verify it still returns a valid response.
    """
    from agentboard.mcp_server import call_tool
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter
    from agentboard.storage.pile_session import SessionWriter

    store = FileStore(tmp_path)
    rid = "run_tfail"
    store.write_iter_artifact(rid, 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    ChapterWriter(store).regen_labor(rid)
    SessionWriter(store).regen(
        rid, goal_title="x", current_phase="tdd_red", total_steps=1, last_verdict="R",
    )

    # Make mcp_calls.jsonl unwritable: create as a directory with that name,
    # which causes open(..., 'a') to fail with IsADirectoryError.
    agentboard = tmp_path / ".agentboard"
    agentboard.mkdir(parents=True, exist_ok=True)
    bad_log = agentboard / "mcp_calls.jsonl"
    bad_log.mkdir()  # directory instead of file → append will fail

    # Primary dispatch must still succeed
    result = await call_tool(
        "agentboard_get_session",
        {"project_root": str(tmp_path), "rid": rid},
    )
    payload = json.loads(result[0].text)
    assert payload["status"] == "ok", f"primary dispatch broken by telemetry: {payload}"
