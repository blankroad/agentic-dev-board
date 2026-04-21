from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class IterationRecord:
    n: int
    plan_text: str = ""
    execution_summary: str = ""
    test_output: str = ""
    diff: str = ""
    verdict: str = ""
    reviewer_feedback: str = ""
    reflect_json: dict = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LoopState:
    goal_id: str
    task_id: str
    goal_description: str
    locked_plan_hash: str
    project_root: str

    iteration: int = 0
    converged: bool = False
    blocked: bool = False
    block_reason: str = ""

    iterations: list[IterationRecord] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0

    def current_record(self) -> IterationRecord | None:
        if self.iterations:
            return self.iterations[-1]
        return None

    def last_verdict(self) -> str:
        rec = self.current_record()
        return rec.verdict if rec else ""

    def last_strategy(self) -> str:
        rec = self.current_record()
        if rec and rec.reflect_json:
            return rec.reflect_json.get("next_strategy", "")
        return ""
