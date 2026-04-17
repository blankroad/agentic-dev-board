"""MCP server exposing devboard's deterministic operations as tools.

Claude Code (or any MCP client) connects via stdio. Tools wrap existing
Python functions — no LLM calls happen inside this server. The client
does all the reasoning; we just provide state management and deterministic
verification.

Run: `python -m devboard.mcp_server` (or via Claude Code's .mcp.json)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from devboard.analytics.retro import generate_retro, save_retro
from devboard.agents.iron_law import check_iron_law
from devboard.gauntlet.lock import build_locked_plan
from devboard.memory.learnings import load_all_learnings, save_learning, search_learnings
from devboard.memory.retriever import load_relevant_learnings
from devboard.models import BoardState, DecisionEntry, Goal, GoalStatus, Task, TaskStatus
from devboard.orchestrator.approval import (
    apply_squash_policy,
    build_pr_body,
    get_diff_stats,
)
from devboard.orchestrator.push import push_and_create_pr
from devboard.orchestrator.verify import verify_checklist
from devboard.replay.replay import branch_run, list_runs
from devboard.storage.file_store import FileStore
from devboard.tools.base import ToolCall
from devboard.tools.careful import check_command

server = Server("devboard")


def _store(project_root: str) -> FileStore:
    return FileStore(Path(project_root).resolve())


def _text(payload: Any) -> list[TextContent]:
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, default=str, indent=2))]


# ══════════════════════════════════════════════════════════════════════════════
# Tool registry
# ══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── State: init & goals ────────────────────────────────────────────────
        Tool(
            name="devboard_init",
            description="Initialize .devboard/ scaffold at the given project root. Creates goals/, runs/, learnings/, retros/ directories and .gitignore entries. Returns the board_id.",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="devboard_add_goal",
            description="Register a new goal. Returns goal_id. If board has no active goal, this one becomes active.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["project_root", "title"],
            },
        ),
        Tool(
            name="devboard_list_goals",
            description="List all goals on the board with their status, title, and task count.",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="devboard_update_task_status",
            description="Update a task's status. Valid: todo, planning, in_progress, reviewing, converged, awaiting_approval, pushed, blocked, failed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "task_id": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["project_root", "task_id", "status"],
            },
        ),

        # ── State: plans ───────────────────────────────────────────────────────
        Tool(
            name="devboard_lock_plan",
            description="Compute SHA256 hash of a decide-output JSON and save as LockedPlan to .devboard/goals/<goal_id>/plan.md and plan.json. Returns {locked_hash, plan_path}. The decide_json must follow the Gauntlet's Decide step schema (problem, non_goals, scope_decision, architecture, known_failure_modes, goal_checklist, out_of_scope_guard, atomic_steps, token_ceiling, max_iterations).",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                    "decide_json": {"type": "object"},
                },
                "required": ["project_root", "goal_id", "decide_json"],
            },
        ),
        Tool(
            name="devboard_load_plan",
            description="Load the LockedPlan for a goal. Returns the full plan including goal_checklist, atomic_steps, out_of_scope_guard, locked_hash.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                },
                "required": ["project_root", "goal_id"],
            },
        ),

        # ── Decisions & diffs ──────────────────────────────────────────────────
        Tool(
            name="devboard_log_decision",
            description="Append a decision entry to .devboard/.../decisions.jsonl. Used to record why (not what) — phase is one of: plan, tdd_red, tdd_green, tdd_refactor, review, cso, redteam, reflect, iron_law, approval.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "task_id": {"type": "string"},
                    "iter": {"type": "integer"},
                    "phase": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "next_strategy": {"type": "string"},
                    "verdict_source": {"type": "string"},
                    "user_hint": {"type": "string"},
                },
                "required": ["project_root", "task_id", "iter", "phase", "reasoning"],
            },
        ),
        Tool(
            name="devboard_load_decisions",
            description="Load all decision entries for a task — used by approval, retro, and RCA for historical context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "task_id": {"type": "string"},
                },
                "required": ["project_root", "task_id"],
            },
        ),
        Tool(
            name="devboard_save_iter_diff",
            description="Save an iteration's diff to .devboard/.../changes/iter_N.diff (for squash-invariant audit).",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "task_id": {"type": "string"},
                    "iter_n": {"type": "integer"},
                    "diff": {"type": "string"},
                },
                "required": ["project_root", "task_id", "iter_n", "diff"],
            },
        ),

        # ── Verification & safety ──────────────────────────────────────────────
        Tool(
            name="devboard_verify",
            description="Deterministic pytest runner. Runs the full suite and produces a VerificationReport: exit code, full_suite_passed, per-checklist-item evidence (matched + passed). NO LLM reasoning — use this when you need fresh evidence that tests are green.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "checklist": {"type": "array", "items": {"type": "string"}},
                    "pytest_bin": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["project_root", "checklist"],
            },
        ),
        Tool(
            name="devboard_check_iron_law",
            description="Inspect a sequence of tool calls to detect TDD Iron Law violations (production code written without a preceding test, or test written AFTER production code). Returns violated, reason, impl_writes, test_writes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_calls": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {"type": "string"},
                                "tool_input": {"type": "object"},
                            },
                        },
                    },
                },
                "required": ["tool_calls"],
            },
        ),
        Tool(
            name="devboard_check_command_safety",
            description="DangerGuard — classify a shell command as safe/warn/block. Hard-blocked: rm -rf /, fork bombs, dd of=/dev/*. Warn: git push --force, DROP TABLE, curl | sh. Use this BEFORE executing any shell command.",
            inputSchema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        ),

        # ── Approval & Push ────────────────────────────────────────────────────
        Tool(
            name="devboard_get_diff_stats",
            description="Get git diff --stat output for the project (uncommitted changes vs HEAD).",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="devboard_build_pr_body",
            description="Build a markdown PR body from LockedPlan + decisions list + iteration count. Auto-summarizes retries, key decisions, checklist.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                    "task_id": {"type": "string"},
                    "iterations_completed": {"type": "integer"},
                    "diff_stats": {"type": "string"},
                },
                "required": ["project_root", "goal_id", "task_id", "iterations_completed"],
            },
        ),
        Tool(
            name="devboard_apply_squash_policy",
            description="Apply a squash policy to a branch: squash (all → 1 commit), semantic (one per task), preserve (keep iter commits), interactive (skip — user does manually).",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "branch": {"type": "string"},
                    "base_branch": {"type": "string"},
                    "policy": {"type": "string", "enum": ["squash", "semantic", "preserve", "interactive"]},
                    "squash_message": {"type": "string"},
                },
                "required": ["project_root", "branch", "base_branch", "policy", "squash_message"],
            },
        ),
        Tool(
            name="devboard_push_pr",
            description="git push -u origin <branch> and gh pr create. Returns PR URL or error. NEVER force-pushes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "branch": {"type": "string"},
                    "pr_title": {"type": "string"},
                    "pr_body": {"type": "string"},
                    "base_branch": {"type": "string"},
                    "draft": {"type": "boolean"},
                },
                "required": ["project_root", "branch", "pr_title", "pr_body"],
            },
        ),

        # ── Learnings ──────────────────────────────────────────────────────────
        Tool(
            name="devboard_save_learning",
            description="Save a tagged learning to .devboard/learnings/<name>.md with frontmatter (tags, category, confidence 0-1, source). Categories: general, bug, pattern, constraint, style.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "category": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source": {"type": "string"},
                },
                "required": ["project_root", "name", "content"],
            },
        ),
        Tool(
            name="devboard_search_learnings",
            description="Search learnings by query, tag, or category. Returns list sorted by confidence descending.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "query": {"type": "string"},
                    "tag": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["project_root"],
            },
        ),
        Tool(
            name="devboard_relevant_learnings",
            description="Retrieve top-N learnings relevant to a goal description. Uses keyword + tag + confidence scoring.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_description": {"type": "string"},
                    "max_learnings": {"type": "integer"},
                },
                "required": ["project_root", "goal_description"],
            },
        ),

        # ── Retro & replay ─────────────────────────────────────────────────────
        Tool(
            name="devboard_generate_retro",
            description="Aggregate stats across goals and runs into a retrospective report. Returns markdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                    "last_n_goals": {"type": "integer"},
                    "save": {"type": "boolean"},
                },
                "required": ["project_root"],
            },
        ),
        Tool(
            name="devboard_list_runs",
            description="List all runs in .devboard/runs/ with metadata (events count, last_iteration, converged, blocked).",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="devboard_replay",
            description="Branch a past run from iteration N. Creates a new run_id, writes replay_start checkpoint, returns (new_run_id, initial_state) for the client to resume.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "source_run_id": {"type": "string"},
                    "from_iteration": {"type": "integer"},
                    "variant_note": {"type": "string"},
                },
                "required": ["project_root", "source_run_id", "from_iteration"],
            },
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tool handlers
# ══════════════════════════════════════════════════════════════════════════════

@server.call_tool()
async def call_tool(name: str, args: dict) -> list[TextContent]:
    try:
        return await _dispatch(name, args)
    except Exception as e:
        return _text({"error": f"{type(e).__name__}: {e}"})


async def _dispatch(name: str, args: dict) -> list[TextContent]:
    # ── init & goals ──────────────────────────────────────────────────────────
    if name == "devboard_init":
        root = Path(args["project_root"]).resolve()
        devboard = root / ".devboard"
        if devboard.exists():
            return _text({"status": "already_initialized", "root": str(root)})
        for d in [devboard / "goals", devboard / "runs", devboard / "learnings", devboard / "retros"]:
            d.mkdir(parents=True)
        store = FileStore(root)
        board = BoardState()
        store.save_board(board)
        # update .gitignore
        gi = root / ".gitignore"
        entries = [".devboard/runs/", ".devboard/state.json", ".devboard/goals/"]
        existing = gi.read_text() if gi.exists() else ""
        additions = [e for e in entries if e not in existing]
        if additions:
            with open(gi, "a") as f:
                f.write("\n# devboard\n" + "\n".join(additions) + "\n")
        return _text({"status": "initialized", "board_id": board.board_id, "root": str(root)})

    if name == "devboard_add_goal":
        store = _store(args["project_root"])
        board = store.load_board()
        goal = Goal(title=args["title"], description=args.get("description", ""))
        board.goals.append(goal)
        if board.active_goal_id is None:
            board.active_goal_id = goal.id
        store.save_goal(goal)
        store.save_board(board)
        return _text({"goal_id": goal.id, "title": goal.title, "active": board.active_goal_id == goal.id})

    if name == "devboard_list_goals":
        store = _store(args["project_root"])
        board = store.load_board()
        goals = [
            {
                "id": g.id, "title": g.title, "status": g.status.value,
                "tasks": len(g.task_ids),
                "active": g.id == board.active_goal_id,
            }
            for g in board.goals
        ]
        return _text({"board_id": board.board_id, "goals": goals})

    if name == "devboard_update_task_status":
        store = _store(args["project_root"])
        # Find task
        board = store.load_board()
        task_id = args["task_id"]
        for goal in board.goals:
            if task_id in goal.task_ids:
                task = store.load_task(goal.id, task_id)
                if task:
                    task.status = TaskStatus(args["status"])
                    store.save_task(task)
                    return _text({"task_id": task_id, "status": task.status.value})
        return _text({"error": f"task {task_id} not found"})

    # ── plans ─────────────────────────────────────────────────────────────────
    if name == "devboard_lock_plan":
        store = _store(args["project_root"])
        plan = build_locked_plan(args["goal_id"], args["decide_json"])
        store.save_locked_plan(plan)
        plan_path = store._goals_dir(args["goal_id"]) / "plan.md"
        return _text({
            "locked_hash": plan.locked_hash,
            "plan_path": str(plan_path),
            "goal_checklist_count": len(plan.goal_checklist),
            "atomic_steps_count": len(plan.atomic_steps),
        })

    if name == "devboard_load_plan":
        store = _store(args["project_root"])
        plan = store.load_locked_plan(args["goal_id"])
        if plan is None:
            return _text({"error": f"no plan for goal {args['goal_id']}"})
        return _text(plan.model_dump())

    # ── decisions & diffs ─────────────────────────────────────────────────────
    if name == "devboard_log_decision":
        store = _store(args["project_root"])
        entry = DecisionEntry(
            iter=args["iter"],
            phase=args["phase"],
            reasoning=args["reasoning"],
            next_strategy=args.get("next_strategy", ""),
            verdict_source=args.get("verdict_source", ""),
            user_hint=args.get("user_hint", ""),
        )
        store.append_decision(args["task_id"], entry)
        return _text({"status": "logged", "phase": args["phase"], "iter": args["iter"]})

    if name == "devboard_load_decisions":
        store = _store(args["project_root"])
        entries = store.load_decisions(args["task_id"])
        return _text([e.model_dump() for e in entries])

    if name == "devboard_save_iter_diff":
        store = _store(args["project_root"])
        store.save_iter_diff(args["task_id"], args["iter_n"], args["diff"])
        return _text({"status": "saved", "task_id": args["task_id"], "iter_n": args["iter_n"]})

    # ── verification & safety ─────────────────────────────────────────────────
    if name == "devboard_verify":
        report = verify_checklist(
            checklist=args["checklist"],
            project_root=Path(args["project_root"]).resolve(),
            pytest_bin=args.get("pytest_bin", "pytest"),
            timeout=args.get("timeout", 120),
        )
        return _text({
            "full_suite_passed": report.full_suite_passed,
            "full_suite_exit": report.full_suite_exit,
            "full_suite_tail": report.full_suite_tail,
            "evidence": [
                {
                    "item": e.item, "passed": e.passed,
                    "matched_item": e.matched_item, "exit_code": e.exit_code,
                }
                for e in report.evidence
            ],
            "all_items_have_evidence": report.all_items_have_evidence,
            "summary_markdown": report.summary(),
        })

    if name == "devboard_check_iron_law":
        calls = [
            ToolCall(tool_name=tc["tool_name"], tool_input=tc["tool_input"], result="")
            for tc in args["tool_calls"]
        ]
        verdict = check_iron_law(calls)
        return _text({
            "violated": verdict.violated,
            "reason": verdict.reason,
            "impl_writes": verdict.impl_writes,
            "test_writes": verdict.test_writes,
        })

    if name == "devboard_check_command_safety":
        verdict = check_command(args["command"])
        return _text({
            "level": verdict.level,
            "pattern": verdict.pattern,
            "reason": verdict.reason,
        })

    # ── approval & push ───────────────────────────────────────────────────────
    if name == "devboard_get_diff_stats":
        stats = get_diff_stats(Path(args["project_root"]).resolve())
        return _text({"diff_stats": stats})

    if name == "devboard_build_pr_body":
        store = _store(args["project_root"])
        plan = store.load_locked_plan(args["goal_id"])
        decisions = store.load_decisions(args["task_id"])
        body = build_pr_body(
            locked_plan=plan,
            decisions=decisions,
            iterations_completed=args["iterations_completed"],
            diff_stats=args.get("diff_stats", ""),
        )
        return _text({"pr_body": body})

    if name == "devboard_apply_squash_policy":
        ok = apply_squash_policy(
            project_root=Path(args["project_root"]).resolve(),
            branch=args["branch"],
            base_branch=args["base_branch"],
            policy=args["policy"],
            squash_message=args["squash_message"],
        )
        return _text({"applied": ok, "policy": args["policy"]})

    if name == "devboard_push_pr":
        result = push_and_create_pr(
            project_root=Path(args["project_root"]).resolve(),
            branch=args["branch"],
            pr_title=args["pr_title"],
            pr_body=args["pr_body"],
            base_branch=args.get("base_branch", "main"),
            draft=args.get("draft", False),
        )
        return _text({
            "success": result.success,
            "pr_url": result.pr_url,
            "branch": result.branch,
            "error": result.error,
        })

    # ── learnings ─────────────────────────────────────────────────────────────
    if name == "devboard_save_learning":
        store = _store(args["project_root"])
        path = save_learning(
            store,
            name=args["name"],
            content=args["content"],
            tags=args.get("tags", []),
            category=args.get("category", "general"),
            confidence=args.get("confidence", 0.5),
            source=args.get("source", ""),
        )
        return _text({"status": "saved", "path": str(path)})

    if name == "devboard_search_learnings":
        store = _store(args["project_root"])
        results = search_learnings(
            store,
            query=args.get("query", ""),
            tag=args.get("tag"),
            category=args.get("category"),
        )
        return _text([
            {
                "name": l.name, "content": l.content, "tags": l.tags,
                "category": l.category, "confidence": l.confidence,
            }
            for l in results
        ])

    if name == "devboard_relevant_learnings":
        store = _store(args["project_root"])
        md = load_relevant_learnings(
            store,
            goal_description=args["goal_description"],
            max_learnings=args.get("max_learnings", 5),
        )
        return _text({"markdown": md})

    # ── retro & replay ────────────────────────────────────────────────────────
    if name == "devboard_generate_retro":
        store = _store(args["project_root"])
        report = generate_retro(
            store,
            goal_id=args.get("goal_id"),
            last_n_goals=args.get("last_n_goals"),
        )
        md = report.to_markdown()
        saved_path = None
        if args.get("save"):
            saved_path = str(save_retro(store, report))
        return _text({"markdown": md, "saved_path": saved_path})

    if name == "devboard_list_runs":
        store = _store(args["project_root"])
        runs = list_runs(store)
        return _text(runs)

    if name == "devboard_replay":
        store = _store(args["project_root"])
        # Need a plan to branch against — assume the source run referenced a goal
        board = store.load_board()
        # Find the goal from the run's first state
        from devboard.orchestrator.checkpointer import Checkpointer
        source_path = store.root / ".devboard" / "runs" / f"{args['source_run_id']}.jsonl"
        cp = Checkpointer(source_path)
        entries = cp.load_all()
        goal_id = None
        for e in entries:
            s = e.get("state") or {}
            if "goal_id" in s:
                goal_id = s["goal_id"]
                break
        if goal_id is None:
            return _text({"error": "could not determine goal_id from source run"})
        plan = store.load_locked_plan(goal_id)
        if plan is None:
            return _text({"error": f"no plan for goal {goal_id}"})
        result = branch_run(
            source_run_id=args["source_run_id"],
            from_iteration=args["from_iteration"],
            store=store,
            locked_plan=plan,
            variant_note=args.get("variant_note", ""),
        )
        if result is None:
            return _text({"error": "checkpoint not found or run missing"})
        new_run_id, initial_state = result
        return _text({
            "new_run_id": new_run_id,
            "goal_id": goal_id,
            "initial_state": initial_state,
        })

    return _text({"error": f"unknown tool: {name}"})


# ══════════════════════════════════════════════════════════════════════════════
# Entry
# ══════════════════════════════════════════════════════════════════════════════

async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
