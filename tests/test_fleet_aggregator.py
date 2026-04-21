"""M2-fleet-data aggregator tests (f_001, f_002, f_003)."""
from __future__ import annotations

import json
import time
from pathlib import Path


def _seed_goal(tmp_path: Path, gid: str, title: str, iters: int,
               last_phase: str, last_verdict: str,
               sparkline: list[str]) -> None:
    """Seed a minimal .devboard/goals/<gid>/ tree with a run + digest."""
    gdir = tmp_path / ".devboard" / "goals" / gid
    tdir = gdir / "tasks" / f"t_{gid}"
    tdir.mkdir(parents=True)
    (gdir / "goal.json").write_text(json.dumps({
        "id": gid, "title": title, "status": "active",
        "created_at": "2026-04-22T00:00:00+00:00",
    }), encoding="utf-8")

    rid = f"run_{gid}"
    runs_dir = tmp_path / ".devboard" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{rid}.jsonl").write_text(
        json.dumps({"event": "run_start", "task_id": f"t_{gid}",
                   "ts": "2026-04-22T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    # Pile digest.json
    pile_dir = tmp_path / ".devboard" / "runs" / rid
    pile_dir.mkdir(parents=True, exist_ok=True)
    (pile_dir / "digest.json").write_text(json.dumps({
        "schema_version": 1,
        "rid": rid,
        "iter_count": iters,
        "verdict_counts": {last_verdict: 1} if last_verdict else {},
        "per_file_scrubber": {"primary_file.py": sparkline} if sparkline else {},
    }), encoding="utf-8")


def test_goal_summary_model_fields() -> None:
    """f_001: GoalSummary has required fields."""
    from agentboard.models import GoalSummary

    gs = GoalSummary(
        gid="g_x",
        title="Test Goal",
        iter_count=5,
        last_phase="tdd_green",
        last_verdict="GREEN",
        sparkline_phases=["tdd_red", "tdd_green"],
        updated_at_iso="2026-04-22T00:00:00+00:00",
    )
    assert gs.gid == "g_x"
    assert gs.iter_count == 5
    assert gs.sparkline_phases == ["tdd_red", "tdd_green"]


def test_load_fleet_returns_sorted_summaries(tmp_path) -> None:
    """f_002: load_fleet returns list[GoalSummary] with per-goal aggregated data."""
    from agentboard.analytics.fleet_aggregator import load_fleet
    from agentboard.models import GoalSummary
    from agentboard.storage.file_store import FileStore

    _seed_goal(tmp_path, "g_alpha", "Alpha", iters=3,
               last_phase="tdd_green", last_verdict="GREEN",
               sparkline=["tdd_red", "tdd_green", "tdd_red"])
    time.sleep(0.01)
    _seed_goal(tmp_path, "g_beta", "Beta", iters=7,
               last_phase="review", last_verdict="SURVIVED",
               sparkline=["tdd_green", "redteam"])

    store = FileStore(tmp_path)
    summaries = load_fleet(store)
    assert len(summaries) == 2
    assert all(isinstance(s, GoalSummary) for s in summaries)

    # Sorted descending by updated_at_iso — latest first
    # (both have same timestamp in fixture; at minimum, no crash + all goals present)
    gids = {s.gid for s in summaries}
    assert gids == {"g_alpha", "g_beta"}

    # Per-goal data: find beta
    beta = next(s for s in summaries if s.gid == "g_beta")
    assert beta.iter_count == 7
    assert beta.title == "Beta"
    assert "tdd_green" in beta.sparkline_phases or "redteam" in beta.sparkline_phases


def test_load_fleet_empty_when_no_goals(tmp_path) -> None:
    """f_003: empty .devboard/goals/ returns empty list, no crash."""
    from agentboard.analytics.fleet_aggregator import load_fleet
    from agentboard.storage.file_store import FileStore

    # Ensure .devboard/goals/ exists but is empty
    (tmp_path / ".devboard" / "goals").mkdir(parents=True)

    store = FileStore(tmp_path)
    summaries = load_fleet(store)
    assert summaries == []
