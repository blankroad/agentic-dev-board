"""MCP server exposing devboard's deterministic operations as tools.

Claude Code (or any MCP client) connects via stdio. Tools wrap existing
Python functions — no LLM calls happen inside this server. The client
does all the reasoning; we just provide state management and deterministic
verification.

Run: `python -m agentboard.mcp_server` (or via Claude Code's .mcp.json)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from agentboard.analytics.metrics import collect_metrics, diagnose_activations
from agentboard.analytics.retro import generate_retro, save_retro
from agentboard.agents.iron_law import check_iron_law
from agentboard.docs.plan_sections import PlanSection, upsert_plan_section
from agentboard.gauntlet.lock import build_locked_plan
from agentboard.memory.learnings import load_all_learnings, save_learning, search_learnings
from agentboard.memory.retriever import load_relevant_learnings
from agentboard.models import BoardState, DecisionEntry, Goal, GoalStatus, Task, TaskStatus
from agentboard.orchestrator.approval import (
    apply_squash_policy,
    build_pr_body,
    get_diff_stats,
)
from agentboard.orchestrator.checkpointer import Checkpointer
from agentboard.orchestrator.push import push_and_create_pr
from agentboard.orchestrator.verify import verify_checklist
from agentboard.replay.replay import branch_run, list_runs
from agentboard.storage.file_store import FileStore
from agentboard.tools.base import ToolCall
from agentboard.tools.careful import check_command

server = Server("agentboard")


def _store(project_root: str) -> FileStore:
    return FileStore(Path(project_root).resolve())


def _text(payload: Any) -> list[TextContent]:
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, default=str, indent=2))]


def _git_identity(project_root: Path) -> tuple[str, str]:
    """Return ``(owner, branch)`` derived from local git config + HEAD ref.

    - owner: ``"Name <email>"`` if both are set; the non-empty one alone if
      only one is; ``"unknown"`` otherwise.
    - branch: short ref name (``git rev-parse --abbrev-ref HEAD``) or
      ``"unknown"`` when HEAD is detached, git is absent, or the directory
      is not a repo.

    Never raises — any OSError/TimeoutExpired/non-zero exit degrades to
    ``"unknown"``. Lock flow must not crash just because git is unhappy.
    """
    import subprocess

    def _run(*cmd: str) -> str:
        try:
            proc = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()

    # Only trust git identity if ``project_root`` is itself a git work tree.
    # Otherwise ``git config`` happily returns the user's global identity,
    # which is misleading for throwaway directories (tests, CI sandboxes).
    in_repo = _run("git", "rev-parse", "--is-inside-work-tree") == "true"
    if not in_repo:
        return "unknown", "unknown"

    name = _run("git", "config", "user.name")
    email = _run("git", "config", "user.email")
    # symbolic-ref works on unborn branches (fresh `git init -b <name>` with
    # zero commits) where `rev-parse --abbrev-ref HEAD` errors out.
    branch = _run("git", "symbolic-ref", "--short", "HEAD")
    if name and email:
        owner = f"{name} <{email}>"
    elif name:
        owner = name
    elif email:
        owner = email
    else:
        owner = "unknown"
    return owner, (branch or "unknown")


# ══════════════════════════════════════════════════════════════════════════════
# Tool registry
# ══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── State: init & goals ────────────────────────────────────────────────
        Tool(
            name="agentboard_init",
            description="Initialize .devboard/ scaffold at the given project root. Creates goals/, runs/, learnings/, retros/ directories and .gitignore entries. Returns the board_id.",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_add_goal",
            description="Register a new goal. Returns goal_id. If board has no active goal, this one becomes active. Optional parent_id must refer to an existing goal; passing an unknown id returns {error}.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_id": {"type": ["string", "null"]},
                },
                "required": ["project_root", "title"],
            },
        ),
        Tool(
            name="agentboard_list_goals",
            description="List all goals on the board with their status, title, and task count.",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_update_task_status",
            description="Update a task's status and optionally merge metadata. Valid statuses: todo, planning, in_progress, reviewing, converged, awaiting_approval, pushed, blocked, failed. Optional `metadata` dict is merged into task.metadata (existing keys preserved, same keys overwritten, absent param leaves metadata untouched).",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "task_id": {"type": "string"},
                    "status": {"type": "string"},
                    "metadata": {"type": "object", "additionalProperties": True},
                },
                "required": ["project_root", "task_id", "status"],
            },
        ),
        Tool(
            name="agentboard_start_task",
            description="Create a new Task for a goal and start a new run. Returns {task_id, run_id}. The run_id is used for subsequent devboard_checkpoint calls. Call this ONCE per implementation session, after devboard_lock_plan but before the first TDD cycle.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                    "title": {"type": "string", "description": "Optional task title, defaults to goal title"},
                    "branch": {"type": "string", "description": "Optional git branch for this task"},
                },
                "required": ["project_root", "goal_id"],
            },
        ),
        Tool(
            name="agentboard_checkpoint",
            description="Append a state-transition event to .devboard/runs/<run_id>.jsonl. Call this at EVERY major skill phase boundary (run_start, plan_complete, tdd_red_complete, tdd_green_complete, tdd_refactor_complete, verify_complete, review_complete, cso_complete, redteam_complete, iteration_complete, converged, blocked). The state dict should capture relevant context for replay/retro.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "run_id": {"type": "string"},
                    "event": {"type": "string", "description": "Event name, e.g. tdd_green_complete, converged, blocked"},
                    "state": {"type": "object", "description": "State snapshot for this transition (freeform dict — iteration, current_step_id, verdict, test outcomes, etc.)"},
                },
                "required": ["project_root", "run_id", "event"],
            },
        ),
        Tool(
            name="agentboard_resume_run",
            description="Load the last checkpoint of a run — used for crash recovery. Returns the most recent non-terminal state so skills can resume where they left off. If the run already has 'converged' or 'blocked' event, returns that instead with can_resume=false.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "run_id": {"type": "string"},
                },
                "required": ["project_root", "run_id"],
            },
        ),

        # ── State: plans ───────────────────────────────────────────────────────
        Tool(
            name="agentboard_lock_plan",
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
            name="agentboard_load_plan",
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
        Tool(
            name="agentboard_verify_plan_integrity",
            description="Recompute the LockedPlan's SHA256 hash and compare against the stored locked_hash. Returns {integrity_ok: bool, stored_hash, computed_hash}. Skills should call this at Gauntlet start and before major iterations to detect tampering or accidental edits to plan.md.",
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
            name="agentboard_log_decision",
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
            name="agentboard_log_parallel_review",
            description=(
                "Record a single combined parallel CSO+redteam review outcome. Writes one "
                "phase='parallel_review' entry to decisions.jsonl with the required parallel-run "
                "metadata fields (parallel_duration_s, cso_duration_s, redteam_duration_s, "
                "cso_verdict, redteam_verdict, overall, overlap_count). Approval Step 0 uses this "
                "single entry instead of separate cso+redteam entries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "task_id": {"type": "string"},
                    "iter": {"type": "integer"},
                    "cso_verdict": {"type": "string"},
                    "redteam_verdict": {"type": "string"},
                    "overall": {"type": "string"},
                    "parallel_duration_s": {"type": "number"},
                    "cso_duration_s": {"type": "number"},
                    "redteam_duration_s": {"type": "number"},
                    "overlap_count": {"type": "integer"},
                    "reasoning": {"type": "string"},
                },
                "required": [
                    "project_root", "task_id", "iter",
                    "cso_verdict", "redteam_verdict", "overall",
                    "parallel_duration_s", "cso_duration_s", "redteam_duration_s",
                    "overlap_count",
                ],
            },
        ),
        Tool(
            name="agentboard_load_decisions",
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
            name="agentboard_save_iter_diff",
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
            name="agentboard_verify",
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
            name="agentboard_check_iron_law",
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
            name="agentboard_check_command_safety",
            description="DangerGuard — classify a shell command as safe/warn/block. Hard-blocked: rm -rf /, fork bombs, dd of=/dev/*. Warn: git push --force, DROP TABLE, curl | sh. Use this BEFORE executing any shell command.",
            inputSchema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        ),
        Tool(
            name="agentboard_check_security_sensitive",
            description="Classify a git diff as security-sensitive using a deterministic category→keyword dictionary (auth, crypto, subprocess, sql, network, deserialization, filesystem). Scans + and - lines, case-insensitive substring match. Returns {sensitive, categories, matches}. Advisory output — used by CSO and approval skills for auto-entry decisions.",
            inputSchema={
                "type": "object",
                "properties": {"diff": {"type": "string"}},
                "required": ["diff"],
            },
        ),
        Tool(
            name="agentboard_check_dependencies",
            description="Audit project dependencies for known CVEs. Detects ecosystem (python via pyproject.toml/requirements.txt, node via package.json), runs pip-audit or npm audit with timeout, parses JSON output. Returns {ecosystem, auditor, severity_counts, findings, skipped_reason}. Severity keys normalized to CRITICAL/HIGH/MEDIUM/LOW. Never raises — controlled errors surface as skipped_reason.",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),

        # ── Approval & Push ────────────────────────────────────────────────────
        Tool(
            name="agentboard_get_diff_stats",
            description="Get git diff --stat output for the project (uncommitted changes vs HEAD).",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_build_pr_body",
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
            name="agentboard_apply_squash_policy",
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
            name="agentboard_push_pr",
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
            name="agentboard_save_learning",
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
            name="agentboard_search_learnings",
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
            name="agentboard_relevant_learnings",
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
            name="agentboard_generate_retro",
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
            name="agentboard_build_overview",
            description="Build OverviewPayload dict from on-disk devboard artifacts (plan.json, brainstorm.md, decisions.jsonl, changes/iter_N.diff, learnings.jsonl). Pure, read-only. Used by TUI center-panel 5-tab view. Returns purpose, plan_digest, iterations, current_state, learnings, followups.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                    "task_id": {"type": ["string", "null"]},
                },
                "required": ["project_root", "goal_id"],
            },
        ),
        Tool(
            name="agentboard_list_runs",
            description="List all runs in .devboard/runs/ with metadata (events count, last_iteration, converged, blocked).",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_metrics",
            description="Per-project metrics dashboard: skill activation counts, convergence rate, iron-law hits, RCA escalations, failure modes. Reads all runs + decisions. Returns structured dict.",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_diagnose",
            description="Diagnostic — did devboard skills actually fire? Compares expected events against observed. Returns skill_activation_score + missing events + suggestions.",
            inputSchema={
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_replay",
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
        Tool(
            name="agentboard_save_brainstorm",
            description="Save brainstorm output for a goal. Writes brainstorm.md (latest alias) and a versioned brainstorm-{ts}.md. Returns error if goal not found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                    "premises": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "existing_code_notes": {"type": "string"},
                },
                "required": ["project_root", "goal_id", "premises", "risks", "alternatives", "existing_code_notes"],
            },
        ),
        Tool(
            name="agentboard_approve_plan",
            description="Record plan review decision. approved=true → status=approved. approved=false requires revision_target (problem|scope|arch|challenge). Returns error if goal not found or approved=false without revision_target.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "revision_target": {"type": "string", "enum": ["problem", "scope", "arch", "challenge"]},
                    "notes": {"type": "string"},
                },
                "required": ["project_root", "goal_id", "approved"],
            },
        ),
        Tool(
            name="agentboard_tui_render_smoke",
            description=(
                "Spawn `devboard board` in a real pty for timeout_s seconds, "
                "send Ctrl+Q, capture output, detect Python tracebacks. "
                "Returns {mounted, crashed, traceback, captured_bytes, duration_s} "
                "or {skipped_reason} if pty/devboard unavailable. POSIX-only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "timeout_s": {"type": "number", "default": 3.0},
                },
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_tui_capture_snapshot",
            description=(
                "Capture a plain-text (and optionally SVG) frame of DevBoardApp "
                "via Textual Pilot in-process. Presses `keys` sequentially after "
                "mount, then extracts compositor output from export_screenshot. "
                "Companion to devboard_tui_render_smoke — smoke is a crash gate, "
                "this is frame extraction. Used by agentboard-ui-preview skill at "
                "Layer 1 (text) and Layer 2 (SVG). Returns {scene_id, text, svg, "
                "saved_txt, saved_svg, crashed, traceback, duration_s}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "scene_id": {"type": "string", "default": "default"},
                    "keys": {"type": "array", "items": {"type": "string"}, "default": []},
                    "save_to": {"type": "string"},
                    "include_svg": {"type": "boolean", "default": False},
                    "fixture_goal_id": {"type": "string"},
                    "timeout_s": {"type": "number", "default": 5.0},
                },
                "required": ["project_root"],
            },
        ),
        Tool(
            name="agentboard_generate_narrative",
            description=(
                "Deterministically assemble plan_summary.md for a goal — a "
                "5-section Purpose/Plan/Process/Result/Review narrative with "
                "per-sentence (source: ...) citations drawn from plan.md + "
                "decisions.jsonl + iter diffs. No LLM calls, no network. "
                "Returns {plan_summary_path, section_citation_counts, total_citations}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "goal_id": {"type": "string"},
                },
                "required": ["project_root", "goal_id"],
            },
        ),
        # ── M2-fleet-data: multi-goal snapshot ──────────────────────────
        Tool(
            name="agentboard_fleet_snapshot",
            description=(
                "Return a compact summary of every goal under .devboard/goals/ "
                "(gid, title, iter_count, last_phase, last_verdict, sparkline_phases, "
                "updated_at_iso). Sorted by updated_at descending. Agent-readable "
                "fleet overview — skip scanning decisions.jsonl / runs manually."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                },
                "required": ["project_root"],
            },
        ),
        # ── M1a-data: Canonical pile read tools (Agent's Diary v3) ───────
        Tool(
            name="agentboard_get_session",
            description=(
                "Return session.md (≤500 tok) for a run's canonical pile. "
                "Index/TOC + per-chapter 1-line teasers + status line. "
                "Returns {status:'error', code:'PILE_ABSENT'|'RID_NOT_FOUND', "
                "hint:...} when pile or rid missing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "rid": {"type": "string"},
                },
                "required": ["project_root", "rid"],
            },
        ),
        Tool(
            name="agentboard_get_chapter",
            description=(
                "Return chapter markdown (≤3k tok) from a run's canonical pile. "
                "chapter must be one of contract|labor|verdict|delta. "
                "Returns {status:'error', code:'CHAPTER_NOT_FOUND'|'PILE_ABSENT'|'RID_NOT_FOUND'} on failure."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {"type": "string"},
                    "rid": {"type": "string"},
                    "chapter": {
                        "type": "string",
                        "enum": ["contract", "labor", "verdict", "delta"],
                    },
                },
                "required": ["project_root", "rid", "chapter"],
            },
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tool handlers
# ══════════════════════════════════════════════════════════════════════════════

def _append_mcp_call_log(project_root: str, entry: dict) -> None:
    """Telemetry for MCP tool calls (M1a-plumbing p_009).

    Writes to .devboard/mcp_calls.jsonl. All errors swallowed — telemetry
    MUST NOT break the primary dispatch path (p_010).
    """
    try:
        log_path = Path(project_root).resolve() / ".devboard" / "mcp_calls.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Deliberately silent — telemetry failure is never a user-visible error.
        pass


@server.call_tool()
async def call_tool(name: str, args: dict) -> list[TextContent]:
    # Accept both `agentboard_*` (canonical) and `devboard_*` (legacy alias)
    # so skills can migrate incrementally and MCP-server restarts don't
    # break in-flight Claude sessions that already cached old tool names.
    original_name = name
    if name.startswith("agentboard_"):
        name = "devboard_" + name[len("agentboard_"):]

    import time as _time
    start = _time.monotonic()
    project_root = args.get("project_root", ".")
    try:
        result = await _dispatch(name, args)
    except Exception as e:
        duration_ms = int((_time.monotonic() - start) * 1000)
        _append_mcp_call_log(project_root, {
            "tool": original_name,
            "ts": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "bytes_returned": 0,
            "error": f"{type(e).__name__}",
        })
        return _text({"error": f"{type(e).__name__}: {e}"})

    duration_ms = int((_time.monotonic() - start) * 1000)
    bytes_returned = sum(len(tc.text) for tc in result) if result else 0
    rid = args.get("rid")
    entry = {
        "tool": original_name,
        "ts": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "bytes_returned": bytes_returned,
    }
    if rid:
        entry["rid"] = rid
    _append_mcp_call_log(project_root, entry)
    return result


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
        parent_id = args.get("parent_id")
        if parent_id is not None:
            if not any(g.id == parent_id for g in board.goals):
                return _text({"error": f"parent_id '{parent_id}' not found"})
        goal = Goal(
            title=args["title"],
            description=args.get("description", ""),
            parent_id=parent_id,
        )
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
                    if args.get("metadata"):
                        task.metadata = {**task.metadata, **args["metadata"]}
                    store.save_task(task)
                    return _text({
                        "task_id": task_id,
                        "status": task.status.value,
                        "metadata": task.metadata,
                    })
        return _text({"error": f"task {task_id} not found"})

    if name == "devboard_start_task":
        import uuid
        from agentboard.models import Task
        store = _store(args["project_root"])
        board = store.load_board()
        goal_id = args["goal_id"]
        goal = board.get_goal(goal_id)
        if goal is None:
            return _text({"error": f"goal {goal_id} not found"})

        task = Task(
            goal_id=goal_id,
            title=args.get("title") or goal.title,
            branch=args.get("branch", ""),
            status=TaskStatus.in_progress,
        )
        goal.task_ids.append(task.id)
        store.save_task(task)
        store.save_goal(goal)
        store.save_board(board)

        run_id = f"run_{uuid.uuid4().hex[:8]}"
        run_path = store.root / ".devboard" / "runs" / f"{run_id}.jsonl"
        cp = Checkpointer(run_path)
        cp.save("run_start", {
            "run_id": run_id,
            "goal_id": goal_id,
            "task_id": task.id,
            "title": task.title,
        })
        return _text({
            "task_id": task.id,
            "run_id": run_id,
            "run_path": str(run_path),
            "goal_id": goal_id,
        })

    if name == "devboard_checkpoint":
        store = _store(args["project_root"])
        run_id = args["run_id"]
        event = args["event"]
        state = args.get("state", {}) or {}
        run_path = store.root / ".devboard" / "runs" / f"{run_id}.jsonl"
        if not run_path.parent.exists():
            run_path.parent.mkdir(parents=True, exist_ok=True)
        cp = Checkpointer(run_path)

        # Order validation — warn (but not block) when an event is logged out of order
        warnings: list[str] = []
        prior_events = [e.get("event") for e in cp.load_all()]
        prior_states = [e.get("state", {}) or {} for e in cp.load_all()]

        # tdd_green_complete requires prior tdd_red_complete for same iteration
        if event == "tdd_green_complete":
            iteration = state.get("iteration")
            if iteration is not None:
                red_for_iter = any(
                    prior_events[i] == "tdd_red_complete"
                    and (prior_states[i].get("iteration") == iteration)
                    for i in range(len(prior_events))
                )
                if not red_for_iter:
                    warnings.append(
                        f"tdd_green_complete logged for iter {iteration} without a prior "
                        f"tdd_red_complete for the same iter. TDD Iron Law requires "
                        f"writing the failing test FIRST and checkpointing RED before GREEN."
                    )

        # tdd_refactor_complete requires prior tdd_green_complete for same iteration
        if event == "tdd_refactor_complete":
            iteration = state.get("iteration")
            if iteration is not None:
                green_for_iter = any(
                    prior_events[i] == "tdd_green_complete"
                    and (prior_states[i].get("iteration") == iteration)
                    for i in range(len(prior_events))
                )
                if not green_for_iter:
                    warnings.append(
                        f"tdd_refactor_complete for iter {iteration} without prior "
                        f"tdd_green_complete. Refactor requires a green baseline."
                    )

        # converged requires at minimum a tdd_complete or tdd_green_complete
        if event == "converged":
            has_tdd_work = any(
                e in ("tdd_complete", "tdd_green_complete", "review_complete")
                for e in prior_events
            )
            if not has_tdd_work:
                warnings.append(
                    "converged logged without any preceding tdd_complete / tdd_green_complete / "
                    "review_complete. Did TDD actually run?"
                )

        # Save the event
        cp.save(event, state)

        # Side-effect: when converged/blocked fires, auto-update task.converged flag
        if event in ("converged", "blocked"):
            # Find task_id from state or prior run_start
            task_id = state.get("task_id")
            if not task_id:
                for e in cp.load_all():
                    s = e.get("state", {}) or {}
                    if s.get("task_id"):
                        task_id = s["task_id"]
                        break
            if task_id:
                try:
                    board = store.load_board()
                    for goal in board.goals:
                        if task_id in goal.task_ids:
                            task = store.load_task(goal.id, task_id)
                            if task:
                                task.converged = (event == "converged")
                                if event == "converged":
                                    task.status = TaskStatus.converged
                                elif event == "blocked":
                                    task.status = TaskStatus.blocked
                                store.save_task(task)
                            break
                except Exception:
                    pass  # non-fatal

        return _text({
            "status": "saved",
            "run_id": run_id,
            "event": event,
            "warnings": warnings,
        })

    if name == "devboard_resume_run":
        store = _store(args["project_root"])
        run_id = args["run_id"]
        run_path = store.root / ".devboard" / "runs" / f"{run_id}.jsonl"
        if not run_path.exists():
            return _text({"error": f"run {run_id} not found", "can_resume": False})
        cp = Checkpointer(run_path)
        entries = cp.load_all()
        if not entries:
            return _text({"can_resume": False, "last_event": None, "state": {}})
        last = entries[-1]
        event = last.get("event", "")
        state = last.get("state", {})
        can_resume = event not in ("converged", "blocked")
        return _text({
            "can_resume": can_resume,
            "last_event": event,
            "event_count": len(entries),
            "state": state,
            "resume_hint": {
                "gauntlet_complete": "continue to agentboard-tdd, start with first atomic step",
                "tdd_red_complete": "GREEN phase next — write minimal impl",
                "tdd_green_complete": "REFACTOR phase next (may skip)",
                "tdd_refactor_complete": "move to next atomic step or verify",
                "iteration_complete": "next iteration",
                "review_complete": "proceed to CSO/redteam based on verdict",
                "cso_complete": "proceed to redteam or commit based on verdict",
            }.get(event, "check last event and resume the natural next phase"),
        })

    # ── plans ─────────────────────────────────────────────────────────────────
    if name == "devboard_lock_plan":
        store = _store(args["project_root"])
        review = store.load_plan_review(args["goal_id"])
        if review is None or review.get("status") != "approved":
            return _text({"error": "plan approval required before locking. Call devboard_approve_plan first."})
        brainstorm_path = store._goals_dir(args["goal_id"]) / "brainstorm.md"
        warnings: list[str] = []
        if not brainstorm_path.exists():
            warnings.append("brainstorm not found — consider running agentboard-brainstorm first")
        plan = build_locked_plan(args["goal_id"], args["decide_json"])
        store.save_locked_plan(plan)
        plan_path = store._goals_dir(args["goal_id"]) / "plan.md"
        # Metadata section (Goal #2 of plan-as-living-doc): write once after
        # lock so the human plan.md carries goal_id, lock timestamp, hash,
        # owner, and branch at its head. Idempotent via upsert_plan_section.
        owner, branch = _git_identity(Path(args["project_root"]))
        metadata_content = (
            f"- Goal ID: {args['goal_id']}\n"
            f"- Locked at: {plan.locked_at.isoformat()}\n"
            f"- Locked hash: {plan.locked_hash}\n"
            f"- Owner: {owner}\n"
            f"- Branch: {branch}"
        )
        upsert_plan_section(plan_path, PlanSection.METADATA, metadata_content)
        return _text({
            "locked_hash": plan.locked_hash,
            "plan_path": str(plan_path),
            "goal_checklist_count": len(plan.goal_checklist),
            "atomic_steps_count": len(plan.atomic_steps),
            "warnings": warnings,
        })

    if name == "devboard_load_plan":
        store = _store(args["project_root"])
        plan = store.load_locked_plan(args["goal_id"])
        if plan is None:
            return _text({"error": f"no plan for goal {args['goal_id']}"})
        return _text(plan.model_dump())

    if name == "devboard_verify_plan_integrity":
        store = _store(args["project_root"])
        plan = store.load_locked_plan(args["goal_id"])
        if plan is None:
            return _text({"error": f"no plan for goal {args['goal_id']}"})
        stored = plan.locked_hash
        computed = plan.compute_hash()
        return _text({
            "integrity_ok": stored == computed,
            "stored_hash": stored,
            "computed_hash": computed,
            "goal_id": args["goal_id"],
        })

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

        # M1a-data (FM7): opt-in iter.json sibling write when rid passed.
        # Preserves existing behavior for legacy callers while powering
        # the canonical pile for new consumers.
        rid = args.get("rid")
        gid = args.get("gid")
        if rid:
            iter_data = {
                "phase": args["phase"],
                "iter_n": args["iter"],
                "ts": datetime.now(timezone.utc).isoformat(),
                "duration_ms": args.get("duration_ms", 0),
                "reasoning": args["reasoning"],
                "verdict_source": args.get("verdict_source", ""),
                "next_strategy": args.get("next_strategy", ""),
            }
            try:
                store.write_iter_artifact(
                    rid, args["iter"], iter_data,
                    gid=gid, tid=args["task_id"],
                )
            except (ValueError, OSError) as exc:
                # Surfacing the error without blocking the legacy log path
                # keeps pile writes best-effort during migration.
                return _text({
                    "status": "logged_partial",
                    "phase": args["phase"],
                    "iter": args["iter"],
                    "pile_error": str(exc),
                })

            # M2-langfuse: optional OTel emission. emit_iter is internally
            # env-gated and swallows all SDK errors — never raises.
            try:
                from agentboard.telemetry import langfuse_emitter
                langfuse_emitter.emit_iter(
                    rid, iter_data, gid=gid, tid=args["task_id"],
                )
            except Exception:
                pass

        return _text({"status": "logged", "phase": args["phase"], "iter": args["iter"]})

    if name == "devboard_log_parallel_review":
        required = [
            "project_root", "task_id", "iter",
            "cso_verdict", "redteam_verdict", "overall",
            "parallel_duration_s", "cso_duration_s", "redteam_duration_s",
            "overlap_count",
        ]
        numeric_fields = [
            "parallel_duration_s", "cso_duration_s", "redteam_duration_s", "overlap_count",
        ]
        missing = [f for f in required if f not in args]
        if missing:
            return _text({
                "status": "error",
                "message": f"missing required field(s): {', '.join(missing)}",
                "missing": missing,
            })
        none_vals = [f for f in required if args.get(f) is None]
        if none_vals:
            return _text({
                "status": "error",
                "message": f"required field(s) must not be None: {', '.join(none_vals)}",
                "null_fields": none_vals,
            })
        bad_types = [
            f for f in numeric_fields
            if isinstance(args.get(f), bool) or not isinstance(args.get(f), (int, float))
        ]
        if bad_types:
            return _text({
                "status": "error",
                "message": f"numeric field(s) have invalid type: {', '.join(bad_types)}",
                "bad_type_fields": bad_types,
            })
        store = _store(args["project_root"])
        payload = {
            "iter": args["iter"],
            "phase": "parallel_review",
            "reasoning": args.get("reasoning", ""),
            "verdict_source": args["overall"],
            "metadata": {
                "cso_verdict": args["cso_verdict"],
                "redteam_verdict": args["redteam_verdict"],
                "overall": args["overall"],
                "parallel_duration_s": args["parallel_duration_s"],
                "cso_duration_s": args["cso_duration_s"],
                "redteam_duration_s": args["redteam_duration_s"],
                "overlap_count": args["overlap_count"],
            },
        }
        store.append_decision(args["task_id"], payload)
        return _text({
            "status": "logged",
            "phase": "parallel_review",
            "iter": args["iter"],
        })

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

    if name == "devboard_check_security_sensitive":
        from agentboard.security.sensitivity import check_security_sensitive
        return _text(check_security_sensitive(args["diff"]))

    if name == "devboard_check_dependencies":
        from agentboard.security.dependencies import check_dependencies
        return _text(check_dependencies(Path(args["project_root"]).resolve()))

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

    if name == "devboard_build_overview":
        from agentboard.analytics.overview_payload import build_overview_payload

        payload = build_overview_payload(
            Path(args["project_root"]).resolve(),
            args["goal_id"],
            task_id=args.get("task_id"),
        )
        return _text(dict(payload))

    if name == "devboard_list_runs":
        store = _store(args["project_root"])
        runs = list_runs(store)
        return _text(runs)

    if name == "devboard_metrics":
        store = _store(args["project_root"])
        m = collect_metrics(store)
        return _text({"dict": m.to_dict(), "markdown": m.to_markdown()})

    if name == "devboard_diagnose":
        store = _store(args["project_root"])
        result = diagnose_activations(store)
        return _text({
            "skill_activation_score": result.skill_activation_score,
            "missing_events": result.missing_events,
            "suggestions": result.suggestions,
            "markdown": result.to_markdown(),
        })

    if name == "devboard_replay":
        store = _store(args["project_root"])
        # Need a plan to branch against — assume the source run referenced a goal
        board = store.load_board()
        # Find the goal from the run's first state
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

    if name == "devboard_save_brainstorm":
        store = _store(args["project_root"])
        goal_id = args["goal_id"]
        if store.load_goal(goal_id) is None:
            return _text({"error": f"goal not found: {goal_id}"})
        store.save_brainstorm(
            goal_id=goal_id,
            premises=args["premises"],
            risks=args["risks"],
            alternatives=args["alternatives"],
            existing_code_notes=args["existing_code_notes"],
        )
        return _text({"status": "saved", "goal_id": goal_id})

    if name == "devboard_approve_plan":
        store = _store(args["project_root"])
        goal_id = args["goal_id"]
        if store.load_goal(goal_id) is None:
            return _text({"error": f"goal not found: {goal_id}"})
        approved = args["approved"]
        revision_target = args.get("revision_target")
        if not approved and not revision_target:
            return _text({"error": "revision_target required when approved=false"})
        store.save_plan_review(goal_id=goal_id, approved=approved, revision_target=revision_target)
        status = "approved" if approved else "revision_pending"
        return _text({"status": status, "goal_id": goal_id})

    if name == "devboard_tui_render_smoke":
        from agentboard.mcp_tools.tui_smoke import run_tui_smoke

        result = run_tui_smoke(
            Path(args["project_root"]).resolve(),
            timeout_s=float(args.get("timeout_s", 3.0)),
        )
        return _text(result)

    if name == "devboard_tui_capture_snapshot":
        from agentboard.mcp_tools.tui_capture import run as run_tui_capture

        result = run_tui_capture(
            project_root=Path(args["project_root"]).resolve(),
            scene_id=args.get("scene_id", "default"),
            keys=list(args.get("keys") or []),
            save_to=args.get("save_to"),
            include_svg=bool(args.get("include_svg", False)),
            fixture_goal_id=args.get("fixture_goal_id"),
            timeout_s=float(args.get("timeout_s", 5.0)),
        )
        return _text(result)

    if name == "devboard_generate_narrative":
        from agentboard.mcp_tools.generate_narrative import run_generate_narrative

        return _text(run_generate_narrative(args))

    # ── M2-fleet-data: fleet snapshot ──────────────────────────────────
    if name == "devboard_fleet_snapshot":
        from agentboard.analytics.fleet_aggregator import load_fleet
        store = _store(args["project_root"])
        summaries = load_fleet(store)
        return _text({
            "goals": [s.model_dump() for s in summaries],
            "total": len(summaries),
        })

    # ── M1a-data: pile read tools ───────────────────────────────────────
    if name == "devboard_get_session":
        store = _store(args["project_root"])
        rid = args["rid"]
        try:
            run_info = store.load_run(rid)
        except ValueError as exc:
            return _text({"status": "error", "code": "BAD_RID", "hint": str(exc)})
        if run_info is None:
            # Distinguish RID_NOT_FOUND vs PILE_ABSENT by checking index
            idx_path = store._rid_index_path()  # type: ignore[attr-defined]
            if idx_path.exists():
                try:
                    idx = json.loads(idx_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    idx = {}
                if rid in idx:
                    return _text({
                        "status": "error",
                        "code": "PILE_ABSENT",
                        "rid": rid,
                        "gid": idx[rid].get("gid"),
                        "hint": f"Run is orphan — run `agentboard rebuild-pile {idx[rid].get('gid')}` (M1a-plumbing CLI)",
                    })
            return _text({
                "status": "error",
                "code": "RID_NOT_FOUND",
                "rid": rid,
                "hint": "rid not in .rid_index.json",
            })
        session_path = run_info["run_dir"] / "session.md"
        if not session_path.exists():
            return _text({
                "status": "error",
                "code": "PILE_ABSENT",
                "rid": rid,
                "hint": "session.md missing — run `agentboard rebuild-pile` (M1a-plumbing CLI)",
            })
        return _text({
            "status": "ok",
            "rid": rid,
            "content": session_path.read_text(encoding="utf-8"),
        })

    if name == "devboard_get_chapter":
        store = _store(args["project_root"])
        rid = args["rid"]
        chapter = args.get("chapter", "").strip().lower()
        valid_chapters = ["contract", "labor", "verdict", "delta"]
        if chapter not in valid_chapters:
            return _text({
                "status": "error",
                "code": "CHAPTER_NOT_FOUND",
                "hint": f"chapter must be one of {valid_chapters}, got {chapter!r}",
                "valid_chapters": valid_chapters,
            })
        try:
            run_info = store.load_run(rid)
        except ValueError as exc:
            return _text({"status": "error", "code": "BAD_RID", "hint": str(exc)})
        if run_info is None:
            return _text({
                "status": "error",
                "code": "RID_NOT_FOUND",
                "rid": rid,
                "hint": "rid not in .rid_index.json or run_dir missing",
            })
        chapter_path = run_info["run_dir"] / "chapters" / f"{chapter}.md"
        if not chapter_path.exists():
            return _text({
                "status": "error",
                "code": "CHAPTER_NOT_FOUND",
                "rid": rid,
                "chapter": chapter,
                "hint": f"chapters/{chapter}.md does not exist (may not be implemented in M1a-data)",
            })
        return _text({
            "status": "ok",
            "rid": rid,
            "chapter": chapter,
            "content": chapter_path.read_text(encoding="utf-8"),
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
