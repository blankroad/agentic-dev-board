from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _uid(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"


class GoalSummary(BaseModel):
    """M2-fleet-data: compact per-goal aggregate for Fleet surface.

    One row per goal showing current state without scanning disk:
    iter count, latest phase / verdict, sparkline of last iters.
    Consumed by agentboard_fleet_snapshot MCP tool + FleetView widget.
    """
    gid: str
    title: str = ""
    iter_count: int = 0
    last_phase: str = ""
    last_verdict: str = ""
    sparkline_phases: list[str] = Field(default_factory=list)
    updated_at_iso: str = ""


class GoalStatus(str, Enum):
    active = "active"
    converged = "converged"
    awaiting_approval = "awaiting_approval"
    pushed = "pushed"
    blocked = "blocked"
    archived = "archived"


class TaskStatus(str, Enum):
    todo = "todo"
    planning = "planning"
    in_progress = "in_progress"
    reviewing = "reviewing"
    converged = "converged"
    awaiting_approval = "awaiting_approval"
    pushed = "pushed"
    failed = "failed"
    blocked = "blocked"


class ReviewVerdict(str, Enum):
    pass_ = "PASS"
    retry = "RETRY"
    replan = "REPLAN"
    escalate = "ESCALATE"


class Iteration(BaseModel):
    number: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    plan_summary: str = ""
    changes_summary: str = ""
    test_report: str = ""
    review_verdict: ReviewVerdict | None = None
    review_notes: str = ""
    redteam_verdict: str = ""
    reflect_reasoning: str = ""
    next_strategy: str = ""
    user_hint: str = ""


class DecisionEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    iter: int
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    phase: str
    reasoning: str
    next_strategy: str = ""
    verdict_source: str = ""
    user_hint: str = ""


class Task(BaseModel):
    id: str = Field(default_factory=lambda: _uid("t"))
    goal_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.todo
    branch: str = ""
    parent_id: str | None = None
    touches: list[str] = Field(default_factory=list)
    forbids: list[str] = Field(default_factory=list)
    iterations: list[Iteration] = Field(default_factory=list)
    converged: bool = False
    retry_count: int = 0
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def current_iteration(self) -> int:
        return len(self.iterations)


class GauntletStep(BaseModel):
    name: str
    completed: bool = False
    content: str = ""
    completed_at: datetime | None = None


class NonGoal(BaseModel):
    """A deferred follow-up — explicitly out of scope for this goal with
    rationale and revisit condition, so future readers (humans or agents)
    understand why and when to come back."""
    item: str
    rationale: str = ""
    revisit_when: str = ""

    def render_line(self) -> str:
        """Render as a plan.md / CLI bullet line, compact when rationale
        and revisit_when are empty (backward-compat with string-shaped
        non_goals)."""
        if not self.rationale and not self.revisit_when:
            return self.item
        parts = [self.item]
        if self.rationale:
            parts.append(f"— {self.rationale}")
        if self.revisit_when:
            parts.append(f"(revisit: {self.revisit_when})")
        return " ".join(parts)


class AtomicStep(BaseModel):
    """A bite-sized TDD step (~2-5 minutes): one behavior, one test, one impl."""
    id: str
    behavior: str                       # "add(1,2) returns 3"
    test_file: str                      # "tests/test_calc.py"
    test_name: str                      # "test_add_two_positives"
    impl_file: str = ""                 # "calculator.py" — may be empty until RED names it
    expected_fail_reason: str = ""      # e.g. "NameError: add not defined"
    completed: bool = False
    # core = the behavior being validated; supporting = scaffolding needed to
    # make the core step pass (fixtures, helper funcs); test_only = adds a
    # regression-proof assertion without changing production code.
    role: Literal["core", "supporting", "test_only"] = "core"


class LockedPlan(BaseModel):
    goal_id: str
    locked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    locked_hash: str = ""
    problem: str = ""
    non_goals: list[NonGoal] = Field(default_factory=list)
    scope_decision: str = ""
    architecture: str = ""
    known_failure_modes: list[str] = Field(default_factory=list)
    goal_checklist: list[str] = Field(default_factory=list)
    out_of_scope_guard: list[str] = Field(default_factory=list)
    atomic_steps: list[AtomicStep] = Field(default_factory=list)
    token_ceiling: int = 500_000
    max_iterations: int = 10
    gauntlet_steps: list[GauntletStep] = Field(default_factory=list)
    integration_test_command: str = ""

    @field_validator("non_goals", mode="before")
    @classmethod
    def _coerce_non_goals(cls, v: Any) -> list[Any]:
        """Accept legacy string-shaped non_goals by wrapping each string into
        {item: <str>}. Existing plans on disk and test fixtures that pass
        list[str] continue to work; new plans use list[{item, rationale,
        revisit_when}]."""
        if not v:
            return []
        out: list[Any] = []
        for entry in v:
            if isinstance(entry, str):
                out.append({"item": entry})
            else:
                out.append(entry)
        return out

    def next_step(self) -> AtomicStep | None:
        for s in self.atomic_steps:
            if not s.completed:
                return s
        return None

    def mark_step_completed(self, step_id: str) -> None:
        for s in self.atomic_steps:
            if s.id == step_id:
                s.completed = True
                return

    def compute_hash(self) -> str:
        content = json.dumps(
            {
                "problem": self.problem,
                # Hash only the `item` string of each non_goal so plans
                # that gained rationale/revisit_when fields produce the same
                # hash as their string-shaped predecessors with identical items.
                "non_goals": [ng.item for ng in self.non_goals],
                "scope_decision": self.scope_decision,
                "architecture": self.architecture,
                "goal_checklist": self.goal_checklist,
                "atomic_steps": [
                    {"id": s.id, "behavior": s.behavior, "test_file": s.test_file, "test_name": s.test_name}
                    for s in self.atomic_steps
                ],
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def lock(self) -> "LockedPlan":
        self.locked_hash = self.compute_hash()
        return self


class Goal(BaseModel):
    id: str = Field(default_factory=lambda: _uid("g"))
    title: str
    description: str = ""
    status: GoalStatus = GoalStatus.active
    branch_prefix: str = ""
    parent_id: str | None = Field(default=None)
    task_ids: list[str] = Field(default_factory=list)
    locked_plan: LockedPlan | None = None
    cost_tokens_used: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BoardState(BaseModel):
    version: int = 1
    board_id: str = Field(default_factory=lambda: _uid("b"))
    active_goal_id: str | None = None
    goals: list[Goal] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_goal(self, goal_id: str) -> Goal | None:
        return next((g for g in self.goals if g.id == goal_id), None)

    def active_goal(self) -> Goal | None:
        if self.active_goal_id:
            return self.get_goal(self.active_goal_id)
        return None
