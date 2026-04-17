from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
import yaml

from devboard.models import BoardState, Goal, GoalStatus, LockedPlan, Task, TaskStatus
from devboard.storage.base import Repository


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically (temp file + rename).

    Safe under concurrent readers — they see either the old complete file
    or the new complete file, never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # NamedTemporaryFile on same dir to guarantee same-FS rename
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


@contextmanager
def file_lock(path: Path, mode: str = "a+"):
    """Advisory exclusive lock on `path` (creates empty file if needed).

    Use around state.json writes to prevent two concurrent Claude Code
    sessions from racing. Lock is released on context exit.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use a dedicated lockfile to avoid blocking the real file
    lock_path = path.with_suffix(path.suffix + ".lock")
    f = open(lock_path, mode)
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        f.close()


class FileStore(Repository):
    def __init__(self, root: Path) -> None:
        self.root = root
        self._devboard = root / ".devboard"

    def _goals_dir(self, goal_id: str) -> Path:
        return self._devboard / "goals" / goal_id

    def _tasks_dir(self, goal_id: str, task_id: str) -> Path:
        return self._goals_dir(goal_id) / "tasks" / task_id

    def _runs_dir(self) -> Path:
        return self._devboard / "runs"

    def _learnings_dir(self) -> Path:
        return self._devboard / "learnings"

    # ── Board ──────────────────────────────────────────────────────────────

    def load_board(self) -> BoardState:
        path = self._devboard / "state.json"
        if not path.exists():
            return BoardState()
        with open(path) as f:
            return BoardState.model_validate_json(f.read())

    def save_board(self, state: BoardState) -> None:
        path = self._devboard / "state.json"
        state.updated_at = datetime.now(timezone.utc)
        with file_lock(path):
            atomic_write(path, state.model_dump_json(indent=2))

    # ── Goal ───────────────────────────────────────────────────────────────

    def load_goal(self, goal_id: str) -> Goal | None:
        path = self._goals_dir(goal_id) / "goal.json"
        if not path.exists():
            return None
        with open(path) as f:
            return Goal.model_validate_json(f.read())

    def save_goal(self, goal: Goal) -> None:
        d = self._goals_dir(goal.id)
        goal.updated_at = datetime.now(timezone.utc)
        atomic_write(d / "goal.json", goal.model_dump_json(indent=2))

    # ── Task ───────────────────────────────────────────────────────────────

    def load_task(self, goal_id: str, task_id: str) -> Task | None:
        path = self._tasks_dir(goal_id, task_id) / "task.json"
        if not path.exists():
            return None
        with open(path) as f:
            return Task.model_validate_json(f.read())

    def save_task(self, task: Task) -> None:
        d = self._tasks_dir(task.goal_id, task.id)
        task.updated_at = datetime.now(timezone.utc)
        atomic_write(d / "task.json", task.model_dump_json(indent=2))
        self._write_task_md(task, d)

    def _write_task_md(self, task: Task, d: Path) -> None:
        checklist = "\n".join(f"- [ ] {item}" for item in [])
        iter_blocks = "\n\n".join(self._render_iteration(it) for it in task.iterations)

        lines = [
            "---",
            f"id: {task.id}",
            f"goal_id: {task.goal_id}",
            f"title: {task.title}",
            f"status: {task.status.value}",
            f"branch: {task.branch}",
            f"iterations: {len(task.iterations)}",
            f"converged: {str(task.converged).lower()}",
            f"retry_count: {task.retry_count}",
            f"created_at: {task.created_at.isoformat()}",
            f"updated_at: {task.updated_at.isoformat()}",
            "---",
            "",
            f"# {task.title}",
            "",
            task.description,
            "",
        ]
        if task.iterations:
            lines += ["## Iterations", "", iter_blocks, ""]

        atomic_write(d / "task.md", "\n".join(lines))

    def _render_iteration(self, it) -> str:
        lines = [
            f"### Iteration {it.number} — {it.started_at.strftime('%Y-%m-%d %H:%M')}",
            f"**Plan**: {it.plan_summary}",
            f"**Changes**: {it.changes_summary}",
            f"**Test**: {it.test_report}",
            f"**Review**: {it.review_verdict or '—'} — {it.review_notes}",
        ]
        if it.reflect_reasoning:
            lines.append(f"**Decision**: {it.reflect_reasoning}")
        if it.user_hint:
            lines.append(f"**User Hint**: {it.user_hint}")
        return "\n".join(lines)

    # ── Locked Plan ────────────────────────────────────────────────────────

    def load_locked_plan(self, goal_id: str) -> LockedPlan | None:
        path = self._goals_dir(goal_id) / "plan.json"
        if not path.exists():
            return None
        with open(path) as f:
            return LockedPlan.model_validate_json(f.read())

    def save_locked_plan(self, plan: LockedPlan) -> None:
        d = self._goals_dir(plan.goal_id)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "plan.json", "w") as f:
            f.write(plan.model_dump_json(indent=2))
        self._write_plan_md(plan, d)

    def _write_plan_md(self, plan: LockedPlan, d: Path) -> None:
        checklist = "\n".join(f"- [ ] {item}" for item in plan.goal_checklist)
        non_goals = "\n".join(f"- {ng}" for ng in plan.non_goals)
        failure_modes = "\n".join(f"- {fm}" for fm in plan.known_failure_modes)
        guard = "\n".join(f"- {g}" for g in plan.out_of_scope_guard)

        content = f"""---
goal_id: {plan.goal_id}
locked_at: {plan.locked_at.isoformat()}
locked_hash: {plan.locked_hash}
token_ceiling: {plan.token_ceiling}
max_iterations: {plan.max_iterations}
---

## Problem
{plan.problem}

## Non-goals
{non_goals}

## Scope Decision
{plan.scope_decision}

## Architecture
{plan.architecture}

## Known Failure Modes
{failure_modes}

## Success Criteria / Goal Checklist
{checklist}

## Out-of-scope Guard
{guard}

## Budget
- token_ceiling: {plan.token_ceiling}
- max_iterations: {plan.max_iterations}
"""
        with open(d / "plan.md", "w") as f:
            f.write(content)

    # ── Audit logs ─────────────────────────────────────────────────────────

    def save_iter_diff(self, task_id: str, iter_n: int, diff: str) -> None:
        board = self.load_board()
        # find which goal owns this task
        goal_id = self._find_goal_for_task(task_id)
        if not goal_id:
            return
        changes_dir = self._tasks_dir(goal_id, task_id) / "changes"
        changes_dir.mkdir(parents=True, exist_ok=True)
        with open(changes_dir / f"iter_{iter_n}.diff", "w") as f:
            f.write(diff)

    def append_decision(self, task_id: str, entry) -> None:
        """Accepts a DecisionEntry or a dict."""
        goal_id = self._find_goal_for_task(task_id)
        if not goal_id:
            return
        d = self._tasks_dir(goal_id, task_id)
        d.mkdir(parents=True, exist_ok=True)
        if hasattr(entry, "model_dump"):
            payload = entry.model_dump()
        elif hasattr(entry, "dict"):
            payload = entry.dict()
        else:
            payload = entry
        with open(d / "decisions.jsonl", "a") as f:
            f.write(json.dumps(payload, default=str) + "\n")

    def load_decisions(self, task_id: str) -> list:
        """Load all decision log entries for a task. Returns list of dicts."""
        from devboard.models import DecisionEntry
        goal_id = self._find_goal_for_task(task_id)
        if not goal_id:
            return []
        path = self._tasks_dir(goal_id, task_id) / "decisions.jsonl"
        if not path.exists():
            return []
        entries = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    entries.append(DecisionEntry(**data))
                except Exception:
                    pass
        return entries

    def save_gauntlet_step(self, goal_id: str, step_name: str, content: str) -> None:
        d = self._goals_dir(goal_id) / "gauntlet"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{step_name}.md", "w") as f:
            f.write(content)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _find_goal_for_task(self, task_id: str) -> str | None:
        board = self.load_board()
        for goal in board.goals:
            if task_id in goal.task_ids:
                return goal.id
        return None

    def list_learnings(self) -> list[Path]:
        d = self._learnings_dir()
        if not d.exists():
            return []
        return sorted(d.glob("*.md"))

    def save_learning(self, name: str, content: str) -> Path:
        d = self._learnings_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{name}.md"
        with open(path, "w") as f:
            f.write(content)
        return path

    def append_run_event(self, run_id: str, event: dict) -> None:
        d = self._runs_dir()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{run_id}.jsonl", "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def load_run_events(self, run_id: str) -> list[dict]:
        path = self._runs_dir() / f"{run_id}.jsonl"
        if not path.exists():
            return []
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events
