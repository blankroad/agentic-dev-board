"""MCP tool tests for M1a-data: get_session, get_chapter, log_decision extension.

Uses pytest-asyncio auto mode (configured in pyproject.toml). Tests dispatch
directly against call_tool() to avoid needing a full MCP client harness.
"""
from __future__ import annotations

import json
from pathlib import Path


async def test_mcp_get_session_all_paths(tmp_path: Path) -> None:
    """agentboard_get_session (s_019):
    - Returns session.md when pile exists
    - Returns PILE_ABSENT stub when rid in index but dir missing (orphan)
    - Returns RID_NOT_FOUND when rid unknown
    """
    from agentboard.mcp_server import call_tool, list_tools
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter
    from agentboard.storage.pile_session import SessionWriter

    tools = await list_tools()
    names = [t.name for t in tools]
    assert "agentboard_get_session" in names

    # Seed a pile
    store = FileStore(tmp_path)
    rid = "run_session_mcp"
    store.write_iter_artifact(rid, 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    ChapterWriter(store).regen_labor(rid)
    SessionWriter(store).regen(
        rid, goal_title="MCP Test", current_phase="tdd_red",
        total_steps=1, last_verdict="RED",
    )

    # Happy path
    result = await call_tool(
        "agentboard_get_session",
        {"project_root": str(tmp_path), "rid": rid},
    )
    payload = json.loads(result[0].text)
    assert payload.get("status") == "ok"
    assert "MCP Test" in payload.get("content", "")

    # RID_NOT_FOUND
    miss = await call_tool(
        "agentboard_get_session",
        {"project_root": str(tmp_path), "rid": "run_does_not_exist"},
    )
    miss_payload = json.loads(miss[0].text)
    assert miss_payload["status"] == "error"
    assert miss_payload["code"] == "RID_NOT_FOUND"

    # PILE_ABSENT (orphan index: delete the run dir)
    import shutil
    shutil.rmtree(tmp_path / ".devboard" / "runs" / rid)
    orphan = await call_tool(
        "agentboard_get_session",
        {"project_root": str(tmp_path), "rid": rid},
    )
    orphan_payload = json.loads(orphan[0].text)
    assert orphan_payload["status"] == "error"
    assert orphan_payload["code"] == "PILE_ABSENT"
    assert "rebuild-pile" in orphan_payload.get("hint", "")


async def test_mcp_get_chapter_enum_and_not_found(tmp_path: Path) -> None:
    """agentboard_get_chapter (s_020):
    - Returns labor.md content on happy path
    - Enum schema in list_tools advertises valid chapter values
    - CHAPTER_NOT_FOUND on unknown chapter (with valid_chapters in hint)
    - Chapter param normalized (strip + lowercase)
    """
    from agentboard.mcp_server import call_tool, list_tools
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter

    # Tool registered with enum
    tools = await list_tools()
    gchap = next((t for t in tools if t.name == "agentboard_get_chapter"), None)
    assert gchap is not None
    enum = gchap.inputSchema["properties"]["chapter"]["enum"]
    assert enum == ["contract", "labor", "verdict", "delta"]

    # Seed a pile + labor chapter
    store = FileStore(tmp_path)
    rid = "run_chapter_mcp"
    store.write_iter_artifact(rid, 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    ChapterWriter(store).regen_labor(rid)

    # Happy path with normalized case
    result = await call_tool(
        "agentboard_get_chapter",
        {"project_root": str(tmp_path), "rid": rid, "chapter": "  LABOR "},
    )
    payload = json.loads(result[0].text)
    assert payload["status"] == "ok"
    assert payload["chapter"] == "labor"
    assert "Chapter" in payload["content"]

    # Unknown chapter
    bad = await call_tool(
        "agentboard_get_chapter",
        {"project_root": str(tmp_path), "rid": rid, "chapter": "files"},
    )
    bad_payload = json.loads(bad[0].text)
    assert bad_payload["status"] == "error"
    assert bad_payload["code"] == "CHAPTER_NOT_FOUND"
    assert "valid_chapters" in bad_payload
    assert "labor" in bad_payload["valid_chapters"]

    # Valid chapter name but file not written (e.g. contract — M1a-data skips)
    missing = await call_tool(
        "agentboard_get_chapter",
        {"project_root": str(tmp_path), "rid": rid, "chapter": "contract"},
    )
    missing_payload = json.loads(missing[0].text)
    assert missing_payload["status"] == "error"
    assert missing_payload["code"] == "CHAPTER_NOT_FOUND"


async def test_log_decision_writes_iter_json_sibling(tmp_path: Path) -> None:
    """agentboard_log_decision (s_021 — FM7 mitigation):
    After call, iter-NNN.json sibling file exists in runs/<rid>/iters/
    alongside the existing decisions.jsonl append.

    The extension must be backward-compat: existing behavior (append to
    decisions.jsonl) is preserved. The new sibling write happens only
    when `rid` is passed in args (opt-in for callers that want pile).
    """
    from agentboard.mcp_server import call_tool

    # Seed goal/task dirs so log_decision's existing path doesn't error
    gid = "g_log_ext"
    tid = "t_log_ext"
    task_dir = tmp_path / ".devboard" / "goals" / gid / "tasks" / tid
    task_dir.mkdir(parents=True)
    (task_dir / "decisions.jsonl").touch()

    rid = "run_log_ext"

    result = await call_tool(
        "agentboard_log_decision",
        {
            "project_root": str(tmp_path),
            "task_id": tid,
            "iter": 7,
            "phase": "tdd_green",
            "reasoning": "test extension",
            "verdict_source": "GREEN_CONFIRMED",
            # Opt-in pile extension: pass rid + gid
            "rid": rid,
            "gid": gid,
        },
    )
    payload = json.loads(result[0].text)
    assert payload.get("status") == "logged"

    # Existing-behavior backward compat: append_decision is invoked on
    # the task_id; see tests in test_decisions_jsonl.py for that path.
    # Here we only verify the NEW behavior (iter.json sibling).

    # New behavior: iter-007.json sibling written to pile
    iter_json = tmp_path / ".devboard" / "runs" / rid / "iters" / "iter-007.json"
    assert iter_json.exists(), "log_decision extension must write iter.json sibling"
    iter_data = json.loads(iter_json.read_text(encoding="utf-8"))
    assert iter_data.get("phase") == "tdd_green"
    assert iter_data.get("iter_n") == 7
    assert iter_data.get("verdict_source") == "GREEN_CONFIRMED"


async def test_integration_5_iter_roundtrip(tmp_path: Path) -> None:
    """End-to-end s_022: inject fake 5-iter sequence via agentboard_log_decision,
    then verify pile artifacts exist + MCP get_session / get_chapter roundtrip.

    Full pipeline proof: Data layer (tri-render + pile + rid-index + digest +
    chapter + session writers) + Agent plumbing (2 MCP tools) work together.
    """
    from agentboard.mcp_server import call_tool
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter
    from agentboard.storage.pile_digest import DigestWriter
    from agentboard.storage.pile_session import SessionWriter
    from agentboard.storage.pile_throttle import ThrottleSentinel

    rid = "run_e2e"
    gid = "g_e2e"
    tid = "t_e2e"
    # Seed task dir so log_decision's legacy path (which we may still
    # exercise via append_decision) doesn't error. Even if goal isn't
    # registered in board, the pile-sibling write should still happen.
    task_dir = tmp_path / ".devboard" / "goals" / gid / "tasks" / tid
    task_dir.mkdir(parents=True)

    # 5 iters via MCP log_decision with pile extension
    phases = [
        ("tdd_red", "RED_CONFIRMED", 1),
        ("tdd_green", "GREEN_CONFIRMED", 2),
        ("tdd_red", "RED_CONFIRMED", 3),
        ("tdd_green", "GREEN_CONFIRMED", 4),
        ("review", "PASS", 5),
    ]
    for phase, verdict, n in phases:
        await call_tool(
            "agentboard_log_decision",
            {
                "project_root": str(tmp_path),
                "task_id": tid,
                "iter": n,
                "phase": phase,
                "reasoning": f"iter {n} {phase}",
                "verdict_source": verdict,
                "rid": rid,
                "gid": gid,
            },
        )

    # Assemble full pile (in real gauntlet this happens as a pipeline
    # after each log_decision; for M1a-data the individual writers are
    # wired up but the orchestration is a future step — invoke manually).
    store = FileStore(tmp_path)
    DigestWriter(store).update(rid)
    ChapterWriter(store).regen_labor(rid)
    SessionWriter(store).regen(
        rid, goal_title="E2E roundtrip", current_phase="review",
        total_steps=22, last_verdict="PASS",
    )

    pile_dir = tmp_path / ".devboard" / "runs" / rid
    # All expected artifacts present
    assert (pile_dir / "iters" / "iter-001.json").exists()
    assert (pile_dir / "iters" / "iter-005.json").exists()
    assert (pile_dir / "digest.json").exists()
    assert (pile_dir / "chapters" / "labor.md").exists()
    assert (pile_dir / "session.md").exists()

    # MCP roundtrip: get_session
    r1 = await call_tool(
        "agentboard_get_session",
        {"project_root": str(tmp_path), "rid": rid},
    )
    p1 = json.loads(r1[0].text)
    assert p1["status"] == "ok"
    assert "E2E roundtrip" in p1["content"]
    assert "labor" in p1["content"].lower()  # teaser present

    # MCP roundtrip: get_chapter("labor")
    r2 = await call_tool(
        "agentboard_get_chapter",
        {"project_root": str(tmp_path), "rid": rid, "chapter": "labor"},
    )
    p2 = json.loads(r2[0].text)
    assert p2["status"] == "ok"
    assert p2["chapter"] == "labor"
    # 5 iter markdown lines must be in the chapter content
    for n in range(1, 6):
        assert f"iter {n}" in p2["content"]

    # Digest has correct iter_count
    digest = json.loads((pile_dir / "digest.json").read_text(encoding="utf-8"))
    assert digest["iter_count"] == 5

    # Throttle sentinel would govern synth orchestration in a real
    # pipeline; demonstrate it's consistent after 5 iters
    sentinel = ThrottleSentinel(store)
    # Synth already happened logically (we wrote chapter/session
    # manually); sentinel monotonic rules for iter 6 same-phase:
    assert sentinel.decide_and_commit(rid, 6, "review") is True  # first call in test scope
