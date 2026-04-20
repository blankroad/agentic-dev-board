"""Build OverviewPayload dict from on-disk devboard artifacts.

Pure, read-only. No LLM calls. Each section (purpose, plan_digest,
iterations, current_state, learnings, followups) is produced by an
independent try/except so partial failures degrade gracefully instead
of erasing all 5 tabs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict


class OverviewPayload(TypedDict):
    purpose: str
    plan_digest: dict[str, object]
    iterations: list[dict[str, object]]
    current_state: dict[str, object]
    learnings: list[dict[str, object]]
    followups: list[str]


_PREMISE_BULLET = re.compile(r"^-\s+(.+?)\s*$")
_DIFF_PLUS_FILE = re.compile(r"^\+\+\+\s+b/(.+)$")


def _extract_purpose(brainstorm_path: Path) -> str:
    try:
        text = brainstorm_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    in_premises = False
    for line in text.splitlines():
        if line.strip().lower().startswith("## premises"):
            in_premises = True
            continue
        if in_premises:
            m = _PREMISE_BULLET.match(line)
            if m:
                return m.group(1)
            if line.startswith("##"):
                break
    return ""


def _extract_touched_files(diff_path: Path) -> list[str]:
    try:
        text = diff_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[str] = []
    for line in text.splitlines():
        m = _DIFF_PLUS_FILE.match(line)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def _diff_stats(diff_path: Path) -> dict[str, int]:
    try:
        text = diff_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"adds": 0, "dels": 0}
    adds = 0
    dels = 0
    for line in text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            adds += 1
        elif line.startswith("-"):
            dels += 1
    return {"adds": adds, "dels": dels}


def _extract_iterations(task_dir: Path) -> list[dict[str, object]]:
    decisions = task_dir / "decisions.jsonl"
    if not decisions.exists():
        return []
    try:
        text = decisions.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    rows: list[dict[str, object]] = []
    seen: dict[int, int] = {}
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        it = entry.get("iter")
        if not isinstance(it, int):
            continue
        diff_path = task_dir / "changes" / f"iter_{it}.diff"
        row = {
            "iter": it,
            "phase": entry.get("phase", ""),
            "verdict": entry.get("verdict_source", ""),
            "ts": entry.get("ts", ""),
            "touched_files": _extract_touched_files(diff_path),
            "diff_stats": _diff_stats(diff_path),
        }
        if it in seen:
            rows[seen[it]] = row
        else:
            seen[it] = len(rows)
            rows.append(row)
    rows.sort(key=lambda r: r["iter"])
    return rows


def _extract_followups(plan_json_path: Path) -> list[str]:
    try:
        data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    ng = data.get("non_goals") or []
    return [str(x) for x in ng if x]


def _extract_learnings(learnings_path: Path) -> list[dict[str, object]]:
    if not learnings_path.exists():
        return []
    try:
        text = learnings_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[dict[str, object]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            out.append(
                {
                    "name": entry.get("name", ""),
                    "content": entry.get("content", ""),
                    "confidence": entry.get("confidence", 0.0),
                }
            )
    return out


def _extract_plan_digest(plan_json_path: Path) -> dict[str, object]:
    try:
        data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    steps = data.get("atomic_steps") or []
    # Strict boolean-True only — plan.json with completed: "false" (string)
    # is truthy in Python and would otherwise inflate the done count.
    done = sum(1 for s in steps if isinstance(s, dict) and s.get("completed") is True)
    step_list = [
        {
            "id": s.get("id", ""),
            "behavior": s.get("behavior", ""),
            "completed": s.get("completed") is True,
        }
        for s in steps
        if isinstance(s, dict)
    ]
    return {
        "locked_hash": data.get("locked_hash", ""),
        "scope_decision": data.get("scope_decision", ""),
        "atomic_steps_total": len(steps),
        "atomic_steps_done": done,
        "atomic_steps": step_list,
    }


def build_overview_payload(
    project_root: Path,
    goal_id: str,
    task_id: str | None = None,
) -> OverviewPayload:
    goal_dir = project_root / ".devboard" / "goals" / goal_id
    try:
        purpose = _extract_purpose(goal_dir / "brainstorm.md")
    except Exception:
        purpose = ""
    try:
        plan_digest = _extract_plan_digest(goal_dir / "plan.json")
    except Exception:
        plan_digest = {}
    iterations: list[dict[str, object]] = []
    if task_id is not None:
        try:
            iterations = _extract_iterations(goal_dir / "tasks" / task_id)
        except Exception:
            iterations = []
    current_state: dict[str, object] = (
        {"status": "awaiting_task"} if task_id is None else {"status": "in_progress"}
    )
    if iterations:
        last = iterations[-1]
        current_state = {
            "status": "in_progress",
            "last_iter": last["iter"],
            "last_phase": last["phase"],
            "last_verdict": last["verdict"],
            "last_ts": last["ts"],
        }
    try:
        followups = _extract_followups(goal_dir / "plan.json")
    except Exception:
        followups = []
    try:
        learnings = _extract_learnings(
            project_root / ".devboard" / "learnings.jsonl"
        )
    except Exception:
        learnings = []
    return OverviewPayload(
        purpose=purpose,
        plan_digest=plan_digest,
        iterations=iterations,
        current_state=current_state,
        learnings=learnings,
        followups=followups,
    )
