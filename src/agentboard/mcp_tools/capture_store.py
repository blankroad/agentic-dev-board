"""Persist agentboard_tui_render_smoke output as text artifacts per goal."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def save_tui_capture(project_root: Path, goal_id: str, capture: dict[str, Any]) -> Path:
    """Write capture dict as text to .devboard/goals/<goal_id>/captures/tui_<ts>.txt.

    Returns the absolute path. Creates captures/ directory if needed.
    """
    captures_dir = Path(project_root) / ".devboard" / "goals" / goal_id / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = captures_dir / f"tui_{ts}.txt"
    lines = [f"{k}: {v}" for k, v in capture.items()]
    path.write_text("\n".join(lines) + "\n")
    return path
