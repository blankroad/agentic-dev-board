"""Fleet aggregator — collect per-goal summaries for the Fleet surface.

Reads .agentboard/goals/*/goal.json + the latest run's digest.json to build
a list of GoalSummary records. All reads are best-effort: corrupt files
are skipped, not propagated as errors. This is the data layer for both
the agentboard_fleet_snapshot MCP tool and the FleetView Textual widget.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentboard.models import GoalSummary

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore


def _latest_run_for_task(runs_dir: Path, task_id: str) -> tuple[Path | None, str]:
    """Return (digest_path, rid) for the latest run jsonl matching task_id."""
    if not runs_dir.exists():
        return None, ""
    candidates: list[tuple[float, str]] = []
    for p in runs_dir.glob("*.jsonl"):
        try:
            first = p.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
            if not first:
                continue
            row = json.loads(first[0])
        except (OSError, json.JSONDecodeError, IndexError):
            continue
        if row.get("task_id") == task_id:
            try:
                candidates.append((p.stat().st_mtime, p.stem))
            except OSError:
                continue
    if not candidates:
        return None, ""
    candidates.sort(reverse=True)
    rid = candidates[0][1]
    digest_path = runs_dir / rid / "digest.json"
    return digest_path if digest_path.exists() else None, rid


def _summarize_goal(gdir: Path, runs_dir: Path) -> GoalSummary | None:
    """Build a GoalSummary for one goal directory. Returns None on skip."""
    try:
        goal_json = gdir / "goal.json"
        if not goal_json.exists():
            return None
        goal_data = json.loads(goal_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    gid = goal_data.get("id", gdir.name)
    title = str(goal_data.get("title", ""))[:200]  # truncate for safety
    updated_at = goal_data.get("created_at", "")

    # Find tasks → latest run per task
    tasks_dir = gdir / "tasks"
    iter_count = 0
    last_phase = ""
    last_verdict = ""
    sparkline: list[str] = []

    if tasks_dir.exists():
        for tdir in sorted(tasks_dir.iterdir()):
            if not tdir.is_dir():
                continue
            tid = tdir.name
            digest_path, _rid = _latest_run_for_task(runs_dir, tid)
            if digest_path is None:
                continue
            try:
                digest = json.loads(digest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            # Latest task's digest wins for phase/verdict; iter_count sums
            iter_count += int(digest.get("iter_count", 0) or 0)
            vc = digest.get("verdict_counts", {})
            if isinstance(vc, dict) and vc:
                # most common verdict wins
                last_verdict = max(vc.items(), key=lambda kv: kv[1])[0]
            # Sparkline: merge per_file_scrubber values, pick longest chain
            scrubber_map = digest.get("per_file_scrubber", {})
            if isinstance(scrubber_map, dict) and scrubber_map:
                # Longest sparkline among files
                for path, phases in scrubber_map.items():
                    if isinstance(phases, list) and len(phases) > len(sparkline):
                        sparkline = list(phases)
                        # Also derive last_phase from end of sparkline
                        if sparkline:
                            last_phase = str(sparkline[-1])

    return GoalSummary(
        gid=gid,
        title=title,
        iter_count=iter_count,
        last_phase=last_phase,
        last_verdict=last_verdict,
        sparkline_phases=sparkline,
        updated_at_iso=updated_at,
    )


def load_fleet(store: "FileStore") -> list[GoalSummary]:
    """Aggregate one GoalSummary per goal under .agentboard/goals/.

    Sorted by updated_at_iso descending (latest first). Corrupt goals
    are silently skipped so the list always renders cleanly.
    """
    goals_dir = store._agentboard / "goals"  # type: ignore[attr-defined]
    runs_dir = store._agentboard / "runs"  # type: ignore[attr-defined]
    if not goals_dir.exists():
        return []

    summaries: list[GoalSummary] = []
    for gdir in sorted(goals_dir.iterdir()):
        if not gdir.is_dir() or gdir.name.startswith("."):
            continue
        summary = _summarize_goal(gdir, runs_dir)
        if summary is not None:
            summaries.append(summary)

    # Stable sort: updated_at descending, then gid ascending for tiebreak
    summaries.sort(key=lambda s: (s.updated_at_iso, s.gid), reverse=True)
    return summaries
