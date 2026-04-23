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

from agentboard.models import BoardState, Goal, GoalStatus, LockedPlan, Task, TaskStatus
from agentboard.storage.base import Repository


def _sanitize_id(id_: str) -> str:
    """Reject path traversal attempts in user-supplied IDs.

    Raises ValueError if the ID contains '..' segments or path separators.
    Returns the ID unchanged if safe.
    """
    if ".." in Path(id_).parts or "/" in id_ or "\\" in id_:
        raise ValueError(f"Unsafe id: {id_!r}")
    return id_


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
    #: Canonical on-disk state root. T4 rename (2026-04-23):
    #: legacy ``.devboard/`` → new ``.agentboard/``. Legacy path
    #: auto-migrated on first FileStore construction if present.
    STATE_DIR_NAME = ".agentboard"
    LEGACY_STATE_DIR_NAME = ".devboard"

    def __init__(self, root: Path) -> None:
        self.root = root
        new_path = root / self.STATE_DIR_NAME
        legacy_path = root / self.LEGACY_STATE_DIR_NAME
        # One-shot migration: if legacy ``.devboard/`` exists and new
        # ``.agentboard/`` does not, atomically rename. Filesystem
        # rename preserves all goal / task / run / learning artifacts.
        if legacy_path.exists() and not new_path.exists():
            try:
                legacy_path.rename(new_path)
            except OSError:
                # Cross-device or permission issue — fall back to
                # silently using the legacy path so the user isn't
                # locked out. Full migration can be retried manually.
                self._agentboard = legacy_path
                return
        self._agentboard = new_path
        # T5 (2026-04-23): per-goal rename of legacy ``gauntlet/``
        # subdirectory → ``phases/``. Runs on every FileStore init but
        # short-circuits cheaply on already-migrated goals (no legacy
        # dir present). Full-chain D1 skills write to ``phases/`` now.
        self._migrate_goal_phase_dirs()

    def _migrate_goal_phase_dirs(self) -> None:
        """Rename legacy ``goals/<gid>/gauntlet/`` → ``goals/<gid>/phases/``.
        Safe to call repeatedly — a goal with no legacy dir, or already
        migrated, is skipped without an exception."""
        goals_root = self._agentboard / "goals"
        if not goals_root.exists():
            return
        for goal_dir in goals_root.iterdir():
            if not goal_dir.is_dir():
                continue
            legacy = goal_dir / "gauntlet"
            new = goal_dir / "phases"
            if legacy.exists() and not new.exists():
                try:
                    legacy.rename(new)
                except OSError:
                    # Keep the legacy dir in place if rename fails;
                    # downstream readers fall back to the older name
                    # via save_gauntlet_step's legacy alias.
                    continue

    def _goals_dir(self, goal_id: str) -> Path:
        return self._agentboard / "goals" / _sanitize_id(goal_id)

    def _tasks_dir(self, goal_id: str, task_id: str) -> Path:
        return self._goals_dir(goal_id) / "tasks" / _sanitize_id(task_id)

    def _runs_dir(self) -> Path:
        return self._agentboard / "runs"

    def _learnings_dir(self) -> Path:
        return self._agentboard / "learnings"

    def _run_pile_dir(self, rid: str) -> Path:
        """Directory for a run's canonical artifact pile (M1a-data)."""
        return self._runs_dir() / _sanitize_id(rid)

    def _rid_index_path(self) -> Path:
        """Global rid → run_path reverse index file."""
        return self._agentboard / ".rid_index.json"

    # ── Pile writers (M1a-data) ──────────────────────────────────────────

    def write_iter_artifact(
        self,
        rid: str,
        iter_n: int,
        data: dict,
        *,
        gid: str | None = None,
        tid: str | None = None,
    ) -> Path:
        """Write a single iter artifact atomically.

        Creates runs/<rid>/iters/iter-NNN.json and returns the path.
        Uses the existing atomic_write primitive (fdatasync + rename)
        for crash safety. Callers should pass dict payloads that round-
        trip through json.dumps/loads cleanly.

        If gid/tid are provided, also updates the global .rid_index.json
        with dir-first ordering: the run dir is created before the index
        entry is written, so an orphan index entry (dir gone) is the
        survivable failure mode rather than an invisible run (dir exists
        but no index entry).
        """
        pile_dir = self._run_pile_dir(rid)
        iters_dir = pile_dir / "iters"
        # Step 1 (dir-first): create directory structure
        iters_dir.mkdir(parents=True, exist_ok=True)
        # Step 2: write iter artifact atomically
        path = iters_dir / f"iter-{iter_n:03d}.json"
        # Schema versioning (M1a-plumbing p_001): add schema_version=1 to
        # outgoing payload so future M2 changes don't silently break M1
        # consumers. Use a shallow copy to avoid mutating caller's dict.
        payload = {"schema_version": 1, **data}
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))
        # Step 3 (index-second): update rid index if gid/tid given
        if gid is not None and tid is not None:
            self._rid_index_upsert(rid, gid=gid, tid=tid)
        return path

    def _rid_index_upsert(self, rid: str, *, gid: str, tid: str) -> None:
        """Add/update an rid → {gid, tid} mapping in .rid_index.json."""
        idx_path = self._rid_index_path()
        self._agentboard.mkdir(parents=True, exist_ok=True)
        with file_lock(idx_path):
            if idx_path.exists():
                try:
                    idx = json.loads(idx_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    idx = {}
            else:
                idx = {}
            idx[_sanitize_id(rid)] = {
                "gid": _sanitize_id(gid),
                "tid": _sanitize_id(tid),
            }
            atomic_write(idx_path, json.dumps(idx, ensure_ascii=False, indent=2))

    def load_run(self, rid: str) -> dict | None:
        """Resolve rid → {rid, gid, tid, run_dir} or None if orphaned.

        Returns None when the index knows rid but the run dir is missing
        (caller should trigger self-heal). Also returns None if the index
        itself has no entry for rid, OR the file is absent.
        """
        rid = _sanitize_id(rid)
        idx_path = self._rid_index_path()
        if not idx_path.exists():
            return None
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        entry = idx.get(rid)
        if entry is None:
            return None
        pile_dir = self._run_pile_dir(rid)
        if not pile_dir.exists():
            # Orphan index: dir missing. Signal self-heal.
            return None
        # Defense-in-depth: symlink / tampered-index attacks may make a
        # path resolve outside .agentboard even after _sanitize_id passes.
        # Reject any resolved path that escapes the agentboard root.
        try:
            resolved = pile_dir.resolve()
            agentboard_resolved = self._agentboard.resolve()
            if not resolved.is_relative_to(agentboard_resolved):
                return None
        except (OSError, ValueError):
            return None
        return {
            "rid": rid,
            "gid": entry.get("gid"),
            "tid": entry.get("tid"),
            "run_dir": pile_dir,
        }

    # ── Board ──────────────────────────────────────────────────────────────

    def load_board(self) -> BoardState:
        path = self._agentboard / "state.json"
        if not path.exists():
            return BoardState()
        with open(path) as f:
            return BoardState.model_validate_json(f.read())

    def save_board(self, state: BoardState) -> None:
        path = self._agentboard / "state.json"
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
        # Non-goals: render as table when any entry carries rationale/revisit,
        # otherwise a flat bullet list (backward-compat with legacy string-shaped plans).
        if plan.non_goals:
            has_detail = any(ng.rationale or ng.revisit_when for ng in plan.non_goals)
            if has_detail:
                rows = [
                    f"| {ng.item} | {ng.rationale or '—'} | {ng.revisit_when or '—'} |"
                    for ng in plan.non_goals
                ]
                non_goals = (
                    "| Item | Rationale | Revisit when |\n"
                    "|---|---|---|\n"
                    + "\n".join(rows)
                )
            else:
                non_goals = "\n".join(f"- {ng.item}" for ng in plan.non_goals)
        else:
            non_goals = "_(none)_"

        # Known failure modes: parse "SEVERITY: body" prefix into a table column
        # when present; otherwise fall back to a flat bullet.
        if plan.known_failure_modes:
            rows = []
            for fm in plan.known_failure_modes:
                if ":" in fm:
                    sev, body = fm.split(":", 1)
                    rows.append(f"| {sev.strip()} | {body.strip()} |")
                else:
                    rows.append(f"| — | {fm} |")
            failure_modes = (
                "| Severity | Mode |\n"
                "|---|---|\n"
                + "\n".join(rows)
            )
        else:
            failure_modes = "_(none)_"

        checklist = (
            "\n".join(f"- [ ] {item}" for item in plan.goal_checklist)
            if plan.goal_checklist else "_(none)_"
        )
        guard = (
            "\n".join(f"- `{g}`" for g in plan.out_of_scope_guard)
            if plan.out_of_scope_guard else "_(none)_"
        )

        # Atomic steps table — previously absent from plan.md (only in plan.json).
        if plan.atomic_steps:
            rows = []
            for s in plan.atomic_steps:
                test_ref = f"`{s.test_file}::{s.test_name}`" if s.test_file else "—"
                impl_ref = f"`{s.impl_file}`" if s.impl_file else "—"
                rows.append(
                    f"| {s.id} | {s.behavior} | {test_ref} | {impl_ref} | {s.role} |"
                )
            atomic_steps_section = (
                "| ID | Behavior | Test | Impl | Role |\n"
                "|---|---|---|---|---|\n"
                + "\n".join(rows)
            )
        else:
            atomic_steps_section = "_(none)_"

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

## Atomic Steps
{atomic_steps_section}

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
        from agentboard.models import DecisionEntry
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

    def save_phase_step(self, goal_id: str, step_name: str, content: str) -> None:
        """Write a phase artifact under ``goals/<gid>/phases/<step>.md``.
        T5 canonical path (2026-04-23); supersedes ``save_gauntlet_step``
        which remains as a deprecated alias."""
        d = self._goals_dir(goal_id) / "phases"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{step_name}.md", "w") as f:
            f.write(content)

    def save_gauntlet_step(self, goal_id: str, step_name: str, content: str) -> None:
        """DEPRECATED T5 alias — forwards to ``save_phase_step``. The
        on-disk path is identical (``phases/``); only the method name
        migrated. Callers should switch to ``save_phase_step``."""
        return self.save_phase_step(goal_id, step_name, content)

    # ── Brainstorm ─────────────────────────────────────────────────────────

    def save_brainstorm(
        self,
        goal_id: str,
        premises: list[str],
        risks: list[str],
        alternatives: list[str],
        existing_code_notes: str,
        scope_mode: str | None = None,
        refined_goal: str | None = None,
        wedge: str | None = None,
        req_list: list[dict] | None = None,
        alternatives_considered: list[dict] | None = None,
        rationale: str | None = None,
        user_confirmed: bool | None = None,
    ) -> None:
        # Input validation runs outside the lock (no disk I/O yet).
        # H0 (redteam MEDIUM fixes 2026-04-23):
        #   - scope_mode must be one of the 4 canonical modes
        #   - req_list items must be dicts with id + text keys
        #   - alternatives_considered[i].chosen must be a boolean, not a
        #     string / int / other truthy sentinel

        _SCOPE_MODES = {"EXPAND", "SELECTIVE", "HOLD", "REDUCE"}
        if scope_mode is not None and scope_mode not in _SCOPE_MODES:
            raise ValueError(
                f"scope_mode must be one of {sorted(_SCOPE_MODES)} "
                f"(got {scope_mode!r})"
            )

        if req_list is not None:
            for i, item in enumerate(req_list):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"req_list[{i}] must be a dict with id + text keys, "
                        f"got {type(item).__name__}"
                    )
                missing = {"id", "text"} - set(item.keys())
                if missing:
                    raise ValueError(
                        f"req_list[{i}] missing required keys: {sorted(missing)}"
                    )

        if alternatives_considered is not None:
            for i, alt in enumerate(alternatives_considered):
                if not isinstance(alt, dict):
                    raise ValueError(
                        f"alternatives_considered[{i}] must be a dict, got {type(alt).__name__}"
                    )
                # chosen, when present, must be a strict bool — not a
                # truthy string like 'true' that may appear after a
                # non-strict JSON transport round-trip.
                if "chosen" in alt and not isinstance(alt["chosen"], bool):
                    raise ValueError(
                        f"alternatives_considered[{i}].chosen must be a bool, "
                        f"got {type(alt['chosen']).__name__}={alt['chosen']!r}"
                    )
            chosen_count = sum(
                1 for alt in alternatives_considered if alt.get("chosen") is True
            )
            if chosen_count != 1:
                raise ValueError(
                    f"alternatives_considered must have exactly one alternative "
                    f"with chosen=true (got {chosen_count})"
                )

        premises_lines = "\n".join(f"- {p}" for p in premises)
        risks_lines = "\n".join(f"- {r}" for r in risks)
        alts_lines = "\n".join(f"- {a}" for a in alternatives)

        d = self._goals_dir(goal_id)
        # B0: acquire the goal-level lock BEFORE sampling the timestamp. This
        # guarantees ts ordering matches write-order, so the lexically newest
        # brainstorm-{ts}.md is the one whose body the alias points to. Without
        # the lock (or with the timestamp sampled outside), two concurrent
        # callers can produce a state where the alias lags behind the newest
        # versioned file.
        with file_lock(d / "brainstorm.md"):
            now = datetime.now(timezone.utc)
            ts = now.isoformat()
            ts_slug = now.strftime("%Y%m%d_%H%M%S_%f")

            fm_fields: dict = {"goal_id": goal_id, "ts": ts}
            if scope_mode is not None:
                fm_fields["scope_mode"] = scope_mode
            if refined_goal is not None:
                fm_fields["refined_goal"] = refined_goal
            if wedge is not None:
                fm_fields["wedge"] = wedge
            if req_list is not None:
                fm_fields["req_list"] = req_list
            if alternatives_considered is not None:
                fm_fields["alternatives_considered"] = alternatives_considered
            if rationale is not None:
                fm_fields["rationale"] = rationale
            if user_confirmed is not None:
                fm_fields["user_confirmed"] = user_confirmed

            fm_yaml = yaml.safe_dump(fm_fields, sort_keys=False, allow_unicode=True)
            content = (
                f"---\n{fm_yaml}---\n"
                f"## Premises\n{premises_lines}\n\n"
                f"## Risks\n{risks_lines}\n\n"
                f"## Alternatives\n{alts_lines}\n\n"
                f"## Existing Code Notes\n{existing_code_notes}\n"
            )
            atomic_write(d / f"brainstorm-{ts_slug}.md", content)
            atomic_write(d / "brainstorm.md", content)

    # ── Plan Review ────────────────────────────────────────────────────────

    def save_plan_review(
        self,
        goal_id: str,
        approved: bool,
        revision_target: str | None = None,
    ) -> None:
        status = "approved" if approved else "revision_pending"
        payload: dict = {"status": status, "ts": datetime.now(timezone.utc).isoformat()}
        if revision_target is not None:
            payload["revision_target"] = revision_target
        d = self._goals_dir(goal_id)
        atomic_write(d / "plan_review.json", json.dumps(payload, indent=2))

    def load_plan_review(self, goal_id: str) -> dict | None:
        path = self._goals_dir(goal_id) / "plan_review.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    # ── Helpers ────────────────────────────────────────────────────────────

    # C1: canonical phase-event verdicts. Used by list_phase_events + TUI
    # phases tab + retro dashboards. Per-cycle events (RED_CONFIRMED,
    # GREEN_CONFIRMED, SKIPPED, REFACTORED) are intentionally NOT phase
    # events — they're iter-level. A phase event marks entry, exit, or
    # terminal state of a D1 phase (intent / frame / architecture /
    # stress / lock / execute / parallel_review / approval / plan).
    PHASE_EVENT_VERDICTS = frozenset({
        "PHASE_START",
        "PHASE_END",
        "PHASE_ABORT",
        "COMPLETED",
        "COMMITTED",
        "DISPATCHED",
        "PASS",
        "RETRY",
        "PUSHED",
        "MERGED",
        "LEGACY_FALLBACK",
        "SCOPE_REVISIT_REQUESTED",
        "BLOCKER_OVERRIDDEN",
    })

    def list_phase_events(self, goal_id: str) -> list[dict]:
        """Aggregate phase-boundary decision entries across all tasks under
        a goal. Returns a list of dicts with fields
        {task_id, phase, iter, verdict_source, reasoning, ts}.
        Per-cycle TDD entries (RED_CONFIRMED, GREEN_CONFIRMED, etc.) are
        filtered out — they're iter-level, not phase-level.

        Uses filesystem-based task discovery (`.agentboard/goals/<gid>/tasks/*`)
        rather than board.state.json traversal so it works even when the
        board index is out of sync with on-disk state.
        """
        events: list[dict] = []
        goal_dir = self._goals_dir(goal_id)
        tasks_dir = goal_dir / "tasks"
        if not tasks_dir.exists():
            return events
        for task_subdir in sorted(tasks_dir.iterdir()):
            if not task_subdir.is_dir():
                continue
            task_id = task_subdir.name
            path = task_subdir / "decisions.jsonl"
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                verdict = data.get("verdict_source", "")
                if verdict not in self.PHASE_EVENT_VERDICTS:
                    continue
                events.append({
                    "task_id": task_id,
                    "phase": data.get("phase", ""),
                    "iter": data.get("iter", 0),
                    "verdict_source": verdict,
                    "reasoning": data.get("reasoning", ""),
                    "ts": data.get("ts", ""),
                })
        return events

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
