"""Pile rebuild helper — reconstructs canonical pile from legacy
decisions.jsonl files for goals that existed before M1a-data shipped.

Used by `agentboard rebuild-pile` CLI. M1a-plumbing scope.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentboard.storage.pile_chapter import ChapterWriter
from agentboard.storage.pile_digest import DigestWriter
from agentboard.storage.pile_session import SessionWriter

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore


class PileAdapter:
    """Maps legacy decisions.jsonl rows → iter.json dict shape.

    Field renames: iter → iter_n. Other preserved fields pass through.
    Phase-specific fields (test_result / verdict / diff_ref / ...) are
    not present in old decisions.jsonl rows, so renderers rely on
    `.get()` defaults when rendering rebuilt pile.
    """

    def decision_to_iter_dict(self, row: dict) -> dict:
        out = dict(row)
        if "iter" in out and "iter_n" not in out:
            out["iter_n"] = out.pop("iter")
        out.setdefault("duration_ms", 0)
        return out


def _rid_for_task(gid: str, tid: str) -> str:
    """Deterministic rid for rebuilt piles — distinguishable from native
    run ids. Keeps gid/tid traceable without a side table.
    """
    # Sanitize characters that _sanitize_id in file_store rejects
    safe_tid = tid.replace("/", "_").replace("\\", "_")
    safe_gid = gid.replace("/", "_").replace("\\", "_")
    return f"rebuilt_{safe_gid}_{safe_tid}"


def _load_decisions(task_dir: Path) -> list[dict]:
    path = task_dir / "decisions.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if isinstance(d, dict):
                rows.append(d)
        except json.JSONDecodeError:
            continue
    return rows


def rebuild_pile_for_goal(store: "FileStore", gid: str) -> dict:
    """Rebuild pile for every task under a goal.

    Returns {status: "ok"|"error", tasks_rebuilt: N, rids: [...], errors: [...]}
    """
    adapter = PileAdapter()
    goal_tasks_dir = store._agentboard / "goals" / gid / "tasks"  # type: ignore[attr-defined]
    if not goal_tasks_dir.exists():
        return {"status": "error", "reason": "no_tasks_dir",
                "tasks_rebuilt": 0, "rids": [], "errors": [f"{gid}: no tasks directory"]}

    rebuilt_rids: list[str] = []
    errors: list[str] = []

    for tid_path in sorted(goal_tasks_dir.iterdir()):
        if not tid_path.is_dir():
            continue
        tid = tid_path.name
        rid = _rid_for_task(gid, tid)
        try:
            rows = _load_decisions(tid_path)
            if not rows:
                continue
            for row in rows:
                iter_dict = adapter.decision_to_iter_dict(row)
                iter_n = iter_dict.get("iter_n", 0)
                if not isinstance(iter_n, int) or iter_n <= 0:
                    # Skip rows with invalid iter_n (e.g., iter=0 sentinel rows)
                    continue
                store.write_iter_artifact(rid, iter_n, iter_dict, gid=gid, tid=tid)
            DigestWriter(store).update(rid)
            ChapterWriter(store).regen_labor(rid)
            SessionWriter(store).regen(
                rid, goal_title=f"rebuilt: {gid}",
                current_phase=str(rows[-1].get("phase", "?")),
                total_steps=len(rows),
                last_verdict=str(rows[-1].get("verdict_source", "?")),
            )
            rebuilt_rids.append(rid)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{tid}: {type(exc).__name__}: {exc}")

    return {
        "status": "ok" if not errors else "partial",
        "tasks_rebuilt": len(rebuilt_rids),
        "rids": rebuilt_rids,
        "errors": errors,
    }


def rebuild_pile_all(store: "FileStore") -> dict:
    """Rebuild pile for every goal. Returns per-goal summary."""
    goals_dir = store._agentboard / "goals"  # type: ignore[attr-defined]
    if not goals_dir.exists():
        return {"status": "error", "reason": "no_goals_dir",
                "goals_rebuilt": 0, "per_goal": {}}

    per_goal: dict[str, dict] = {}
    for gid_path in sorted(goals_dir.iterdir()):
        if not gid_path.is_dir():
            continue
        gid = gid_path.name
        if gid.startswith("."):
            continue
        per_goal[gid] = rebuild_pile_for_goal(store, gid)

    return {
        "status": "ok",
        "goals_rebuilt": len(per_goal),
        "per_goal": per_goal,
    }
