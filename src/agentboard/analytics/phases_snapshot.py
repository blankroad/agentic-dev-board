"""C2 phases snapshot — goals × phases matrix for the TUI phases tab.

Aggregates decisions.jsonl phase events from every task under every goal
and produces a compact structure:

    {
      "goals": [
        {
          "id": "g_xxx",
          "title": "...",
          "phases": {
            "intent":       "COMPLETED" | "RUNNING" | "BLOCKED" | "NOT_STARTED",
            "frame":        "...",
            "architecture": "...",
            "stress":       "...",
            "lock":         "...",
            "execute":      "...",
            "parallel_review": "...",
            "approval":     "...",
          },
          "latest_event": {phase, verdict_source, ts} | None,
        },
        ...
      ],
      "phases_order": ["intent", "frame", "architecture", "stress", "lock",
                       "execute", "parallel_review", "approval"],
    }

State mapping rule (per (goal, phase) cell):
- `COMPLETED`    → any terminal verdict for that phase: PHASE_END, COMPLETED,
                   COMMITTED, DISPATCHED, MERGED, PUSHED, PASS
- `RUNNING`      → PHASE_START observed without a terminal follow-up
- `BLOCKED`      → PHASE_ABORT or RETRY observed as the latest event
- `NOT_STARTED`  → no phase events for that (goal, phase)

Pure function — no I/O side effects beyond reading the .agentboard tree.
"""
from __future__ import annotations

from pathlib import Path

from agentboard.storage.file_store import FileStore


# Canonical phase order in the D1 chain + post-chain pipeline.
PHASES_ORDER = [
    "intent",
    "frame",
    "architecture",
    "stress",
    "lock",
    "execute",
    "parallel_review",
    "approval",
]

_TERMINAL_VERDICTS = frozenset({
    "PHASE_END",
    "COMPLETED",
    "COMMITTED",
    "DISPATCHED",
    "MERGED",
    "PUSHED",
    "PASS",
})

_BLOCKED_VERDICTS = frozenset({
    "PHASE_ABORT",
    "RETRY",
    "BLOCKER_OVERRIDDEN",
    "SCOPE_REVISIT_REQUESTED",
})


def phases_snapshot(project_root: Path | str) -> dict:
    """Build the goals × phases matrix for the given project root.

    Uses filesystem-based task discovery (FileStore.list_phase_events) so
    it works even when board.state.json is out of sync.
    """
    project_root = Path(project_root)
    store = FileStore(project_root)

    goals_dir = project_root / ".agentboard" / "goals"
    goal_rows: list[dict] = []

    if not goals_dir.exists():
        return {"goals": [], "phases_order": list(PHASES_ORDER)}

    for goal_dir in sorted(goals_dir.iterdir()):
        if not goal_dir.is_dir():
            continue
        goal_id = goal_dir.name
        goal_obj = store.load_goal(goal_id)
        title = goal_obj.title if goal_obj is not None else goal_id

        events = store.list_phase_events(goal_id)

        # Per-phase state derivation. Walk events in order; latest wins.
        per_phase: dict[str, str] = {p: "NOT_STARTED" for p in PHASES_ORDER}
        latest: dict | None = None

        for ev in events:
            phase = ev["phase"]
            if phase not in per_phase:
                # Unknown phase label (e.g. legacy "plan"); skip
                continue
            verdict = ev["verdict_source"]
            if verdict in _TERMINAL_VERDICTS:
                per_phase[phase] = "COMPLETED"
            elif verdict in _BLOCKED_VERDICTS:
                per_phase[phase] = "BLOCKED"
            elif verdict == "PHASE_START":
                # Only mark RUNNING if we haven't seen terminal/blocked yet.
                if per_phase[phase] == "NOT_STARTED":
                    per_phase[phase] = "RUNNING"
            latest = ev

        goal_rows.append({
            "id": goal_id,
            "title": title,
            "phases": per_phase,
            "latest_event": (
                {
                    "phase": latest["phase"],
                    "verdict_source": latest["verdict_source"],
                    "ts": latest["ts"],
                }
                if latest
                else None
            ),
        })

    return {"goals": goal_rows, "phases_order": list(PHASES_ORDER)}
