from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Checkpointer:
    """Append-only JSONL checkpoint store for run state transitions."""

    def __init__(self, run_path: Path) -> None:
        self._path = run_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, event: str, state: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "state": _sanitize(state),
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def load_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        entries = []
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries

    def last_state(self) -> dict | None:
        entries = self.load_all()
        for e in reversed(entries):
            if "state" in e:
                return e["state"]
        return None

    def find_resume_point(self) -> tuple[int, dict] | None:
        """Return (iteration, state) of the last completed iteration, if any."""
        entries = self.load_all()
        for e in reversed(entries):
            if e.get("event") == "iteration_complete" and "state" in e:
                s = e["state"]
                return s.get("iteration", 0), s
        return None


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if hasattr(obj, "value"):
        return obj.value
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj
