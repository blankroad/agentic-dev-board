from __future__ import annotations

import json
from pathlib import Path

from agentboard.llm.client import BudgetTracker


def load_budget(goal_id: str, devboard_dir: Path) -> BudgetTracker | None:
    path = devboard_dir / "goals" / goal_id / "budget.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    tracker = BudgetTracker(
        goal_id=data["goal_id"],
        token_ceiling=data["token_ceiling"],
        tokens_used=data["tokens_used"],
        cost_usd=data["cost_usd"],
        calls=data.get("calls", []),
    )
    return tracker


def save_budget(tracker: BudgetTracker, devboard_dir: Path) -> None:
    d = devboard_dir / "goals" / tracker.goal_id
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "budget.json", "w") as f:
        json.dump({
            "goal_id": tracker.goal_id,
            "token_ceiling": tracker.token_ceiling,
            "tokens_used": tracker.tokens_used,
            "cost_usd": tracker.cost_usd,
            "calls": tracker.calls,
        }, f, indent=2)
