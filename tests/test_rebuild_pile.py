"""M1a-plumbing tests for PileAdapter + rebuild_pile_for_goal + CLI + e2e.

Covers p_004 through p_008 and p_012.
"""
from __future__ import annotations

import json
from pathlib import Path


def test_pile_adapter_maps_all_historical_phases(tmp_path) -> None:
    """p_004: PileAdapter.decision_to_iter_dict renames iter→iter_n and
    preserves phase / ts / reasoning / verdict_source across all historical
    phases (tdd_red/tdd_green/tdd_refactor/review/cso/redteam/approval).

    guards: F1 redteam-finding analog (type / field mismatch)
    """
    from agentboard.storage.pile_rebuild import PileAdapter

    adapter = PileAdapter()
    for phase in ("tdd_red", "tdd_green", "tdd_refactor", "review",
                  "cso", "redteam", "approval", "plan", "brainstorm"):
        row = {
            "iter": 3,
            "ts": "2026-04-21T14:07:06Z",
            "phase": phase,
            "reasoning": "test",
            "next_strategy": "",
            "verdict_source": "OK",
            "user_hint": "",
        }
        out = adapter.decision_to_iter_dict(row)
        # Key rename
        assert out["iter_n"] == 3, f"iter_n not mapped for {phase}"
        assert "iter" not in out, f"iter not removed for {phase}"
        # Preserved fields
        assert out["phase"] == phase
        assert out["ts"] == "2026-04-21T14:07:06Z"
        assert out["reasoning"] == "test"
        assert out["verdict_source"] == "OK"


def test_rebuild_pile_produces_valid_pile(tmp_path) -> None:
    """p_005: rebuild_pile_for_goal replays decisions.jsonl and produces
    iter.json files + digest + chapter + session.
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_rebuild import rebuild_pile_for_goal

    # Seed a goal with decisions.jsonl but no pile
    store = FileStore(tmp_path)
    gid = "g_rb"
    tid = "t_rb"
    task_dir = tmp_path / ".agentboard" / "goals" / gid / "tasks" / tid
    task_dir.mkdir(parents=True)
    with open(task_dir / "decisions.jsonl", "w") as f:
        for n, phase in enumerate(
            ["tdd_red", "tdd_green", "review", "redteam", "approval"], start=1
        ):
            f.write(json.dumps({
                "iter": n,
                "ts": f"2026-04-21T14:0{n}:00Z",
                "phase": phase,
                "reasoning": f"step {n}",
                "next_strategy": "",
                "verdict_source": "GREEN" if "green" in phase else "OK",
                "user_hint": "",
            }) + "\n")

    summary = rebuild_pile_for_goal(store, gid)
    assert summary["status"] == "ok"
    assert summary["tasks_rebuilt"] >= 1

    # Verify pile artifacts
    rid = summary["rids"][0]
    pile = tmp_path / ".agentboard" / "runs" / rid
    assert (pile / "iters" / "iter-001.json").exists()
    assert (pile / "iters" / "iter-005.json").exists()
    assert (pile / "digest.json").exists()
    assert (pile / "chapters" / "labor.md").exists()
    assert (pile / "session.md").exists()


def test_rebuild_pile_idempotent(tmp_path) -> None:
    """p_006: rebuild_pile_for_goal is byte-identical on 2nd run."""
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_rebuild import rebuild_pile_for_goal

    store = FileStore(tmp_path)
    gid = "g_idem"
    tid = "t_idem"
    task_dir = tmp_path / ".agentboard" / "goals" / gid / "tasks" / tid
    task_dir.mkdir(parents=True)
    with open(task_dir / "decisions.jsonl", "w") as f:
        for n in range(1, 4):
            f.write(json.dumps({
                "iter": n, "ts": f"2026-04-21T14:0{n}:00Z",
                "phase": "tdd_red", "reasoning": f"r{n}",
                "next_strategy": "", "verdict_source": "RED", "user_hint": "",
            }) + "\n")

    s1 = rebuild_pile_for_goal(store, gid)
    rid = s1["rids"][0]
    digest1 = (tmp_path / ".agentboard" / "runs" / rid / "digest.json").read_bytes()

    s2 = rebuild_pile_for_goal(store, gid)
    digest2 = (tmp_path / ".agentboard" / "runs" / rid / "digest.json").read_bytes()
    assert digest1 == digest2, "rebuild_pile drift on 2nd run"


def test_cli_rebuild_pile_single_gid(tmp_path) -> None:
    """p_007: `agentboard rebuild-pile <gid>` via Typer CliRunner."""
    from typer.testing import CliRunner

    from agentboard.cli import app
    from agentboard.storage.file_store import FileStore

    # Seed
    store = FileStore(tmp_path)
    gid = "g_cli"
    tid = "t_cli"
    task_dir = tmp_path / ".agentboard" / "goals" / gid / "tasks" / tid
    task_dir.mkdir(parents=True)
    (task_dir / "decisions.jsonl").write_text(
        json.dumps({
            "iter": 1, "ts": "2026-04-21T14:00:00Z", "phase": "tdd_red",
            "reasoning": "r", "next_strategy": "", "verdict_source": "R",
            "user_hint": "",
        }) + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["rebuild-pile", gid, "--root", str(tmp_path)],
    )
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    assert (tmp_path / ".agentboard" / "runs").exists()
    # At least one run dir created under runs/
    runs = list((tmp_path / ".agentboard" / "runs").iterdir())
    assert any(r.is_dir() for r in runs), "no run dir produced"


def test_cli_rebuild_pile_all(tmp_path) -> None:
    """p_008: `agentboard rebuild-pile --all` rebuilds every goal + summary."""
    from typer.testing import CliRunner

    from agentboard.cli import app

    # Seed 2 goals
    for gid in ("g_all_1", "g_all_2"):
        task_dir = tmp_path / ".agentboard" / "goals" / gid / "tasks" / f"t_{gid}"
        task_dir.mkdir(parents=True)
        (task_dir / "decisions.jsonl").write_text(
            json.dumps({
                "iter": 1, "ts": "2026-04-21T14:00:00Z", "phase": "tdd_red",
                "reasoning": "r", "next_strategy": "", "verdict_source": "R",
                "user_hint": "",
            }) + "\n",
            encoding="utf-8",
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["rebuild-pile", "--all", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0, f"CLI --all failed: {result.output}"
    assert "g_all_1" in result.output
    assert "g_all_2" in result.output


def test_integration_rebuild_then_get_session(tmp_path) -> None:
    """p_012 E2E: seed orphan goal (decisions only) → rebuild-pile →
    agentboard_get_session returns ok with valid content.
    """
    from agentboard.mcp_server import call_tool
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_rebuild import rebuild_pile_for_goal
    import asyncio

    store = FileStore(tmp_path)
    gid = "g_e2e_rb"
    tid = "t_e2e_rb"
    task_dir = tmp_path / ".agentboard" / "goals" / gid / "tasks" / tid
    task_dir.mkdir(parents=True)
    with open(task_dir / "decisions.jsonl", "w") as f:
        for n in range(1, 4):
            f.write(json.dumps({
                "iter": n, "ts": f"2026-04-21T14:0{n}:00Z",
                "phase": "tdd_red" if n < 3 else "review",
                "reasoning": f"iter {n}",
                "next_strategy": "", "verdict_source": "OK", "user_hint": "",
            }) + "\n")

    summary = rebuild_pile_for_goal(store, gid)
    rid = summary["rids"][0]

    # MCP roundtrip
    result = asyncio.run(call_tool(
        "agentboard_get_session",
        {"project_root": str(tmp_path), "rid": rid},
    ))
    payload = json.loads(result[0].text)
    assert payload["status"] == "ok"
    assert "content" in payload
    # Chapter also accessible
    c = asyncio.run(call_tool(
        "agentboard_get_chapter",
        {"project_root": str(tmp_path), "rid": rid, "chapter": "labor"},
    ))
    cp = json.loads(c[0].text)
    assert cp["status"] == "ok"
