from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SessionContext:
    """Read-only facade over .devboard/ state used by every v2.1 pane.

    Resolves the "active" goal/task for rendering and exposes pre-parsed
    decision rows + touched-file lists. All methods are side-effect free
    and tolerate missing/malformed files (degrade to empty result).

    `active_goal_id` resolution order:
    1. explicit override set via `set_active_goal(gid)` (populated by
       commands like `:goto` so widgets reflect user intent)
    2. latest plan.md mtime on disk (default on first load)
    3. None if no goal dirs exist
    """

    def __init__(self, store_root: Path) -> None:
        self.store_root = store_root
        self._agentboard = store_root / ".devboard"
        self._goals_dir = self._agentboard / "goals"
        self._override_goal_id: str | None = None

    def set_active_goal(self, goal_id: str | None) -> None:
        """Pin the active goal regardless of disk mtime. Pass None to
        fall back to latest-mtime resolution."""
        self._override_goal_id = goal_id

    @property
    def active_goal_id(self) -> str | None:
        if self._override_goal_id is not None:
            return self._override_goal_id
        if not self._goals_dir.exists():
            return None
        candidates: list[tuple[float, str]] = []
        for goal_dir in self._goals_dir.iterdir():
            if not goal_dir.is_dir():
                continue
            plan = goal_dir / "plan.md"
            if plan.exists():
                candidates.append((plan.stat().st_mtime, goal_dir.name))
            else:
                candidates.append((goal_dir.stat().st_mtime - 1e12, goal_dir.name))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def decisions_for_task(self, task_id: str) -> list[dict[str, Any]]:
        """Parsed decisions.jsonl rows for a task, sorted by iter desc."""
        gid = self.active_goal_id
        if not gid:
            return []
        path = self._goals_dir / gid / "tasks" / task_id / "decisions.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        for raw_line in text.splitlines():
            if not raw_line.strip():
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                rows.append(entry)
        rows.sort(key=lambda d: d.get("iter", -1), reverse=True)
        return rows

    def all_goals(self) -> list[dict[str, Any]]:
        """Goals as stored in state.json (list of {id, title, status}).
        Returns empty list if state.json is missing/malformed."""
        state_file = self._agentboard / "state.json"
        if not state_file.exists():
            return []
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return []
        raw = data.get("goals", [])
        return [g for g in raw if isinstance(g, dict) and "id" in g]

    def files_changed_in_iter(self, task_id: str, iter_n: int) -> list[str]:
        """Parse iter_N.diff and return unique touched file paths."""
        gid = self.active_goal_id
        if not gid:
            return []
        diff_path = (
            self._goals_dir / gid / "tasks" / task_id / "changes" / f"iter_{iter_n}.diff"
        )
        if not diff_path.exists():
            return []
        try:
            text = diff_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        files: list[str] = []
        seen: set[str] = set()
        for line in text.splitlines():
            m = re.match(r"^\+\+\+ b/(.+)$", line)
            if m:
                p = m.group(1)
                if p not in seen:
                    seen.add(p)
                    files.append(p)
        return files
