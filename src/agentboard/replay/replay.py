from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from agentboard.orchestrator.checkpointer import Checkpointer
from agentboard.orchestrator.state import LoopState
from agentboard.models import LockedPlan
from agentboard.storage.file_store import FileStore


@dataclass
class ReplaySpec:
    source_run_id: str
    from_iteration: int
    variant_note: str = ""
    new_run_id: str = ""


def find_state_at_iteration(checkpointer: Checkpointer, target_iter: int) -> dict | None:
    """Find the graph state snapshot after iteration N completed."""
    entries = checkpointer.load_all()
    best: dict | None = None
    for e in entries:
        if e.get("event") == "iteration_complete":
            s = e.get("state", {})
            if s.get("iteration", 0) - 1 <= target_iter:
                best = s
    return best


def branch_run(
    source_run_id: str,
    from_iteration: int,
    store: FileStore,
    locked_plan: LockedPlan,
    variant_note: str = "",
    new_run_id: str | None = None,
) -> tuple[str, dict] | None:
    """Load state at from_iteration and return (new_run_id, initial_state) for a new run.

    The caller passes this initial_state to run_loop(...) to replay from that point.
    Returns None if checkpoint not found.
    """
    source_path = store.root / ".devboard" / "runs" / f"{source_run_id}.jsonl"
    if not source_path.exists():
        return None

    cp = Checkpointer(source_path)
    state = find_state_at_iteration(cp, from_iteration)
    if state is None:
        return None

    new_id = new_run_id or f"replay_{uuid.uuid4().hex[:8]}"

    # Write provenance to new run file before returning
    new_path = store.root / ".devboard" / "runs" / f"{new_id}.jsonl"
    new_cp = Checkpointer(new_path)
    new_cp.save("replay_start", {
        "source_run_id": source_run_id,
        "from_iteration": from_iteration,
        "variant_note": variant_note,
        "branched_state": state,
    })

    # Reset convergence/blocked flags so loop runs fresh from this point
    replay_state = {
        **state,
        "converged": False,
        "blocked": False,
        "block_reason": "",
        "verdict": "",
        "reviewer_feedback": "",
        "reflect_json": state.get("reflect_json", {}),
        "iteration": from_iteration + 1,
    }
    return new_id, replay_state


def list_runs(store: FileStore) -> list[dict]:
    """List all run files with basic metadata."""
    runs_dir = store.root / ".devboard" / "runs"
    if not runs_dir.exists():
        return []
    result = []
    for p in sorted(runs_dir.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        cp = Checkpointer(p)
        entries = cp.load_all()
        events = [e.get("event") for e in entries]
        last_iter = 0
        for e in reversed(entries):
            s = e.get("state", {})
            if "iteration" in s:
                last_iter = s["iteration"]
                break
        converged = "converged" in events
        blocked = "blocked" in events
        result.append({
            "run_id": p.stem,
            "events": len(entries),
            "last_iteration": last_iter,
            "converged": converged,
            "blocked": blocked,
            "mtime": p.stat().st_mtime,
        })
    return result
