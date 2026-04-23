---
name: agentboard-lock
description: D1e SKELETON (2026-04-23). Mechanical synthesis — takes prior phase artifacts, decomposes into atomic_steps, computes SHA256 via build_locked_plan, writes plan.md + plan.json, starts task + run, logs gauntlet_complete checkpoint. No LLM re-decisions — scope_decision is injected from brainstorm.md verbatim. Hands off to execution (agentboard-tdd for now; future agentboard-execute). Do NOT invoke until skeleton filled — status=skeleton.
when_to_use: After agentboard-stress completes (+ any replan loops settled). Auto-invoked in the D1 chain. Pre-cutover, invoke only when explicitly asked.
---

> **Language**: Respond to the user in Korean. Code, file paths, variable names in English.

> **Status (2026-04-23, SKELETON):** D1e scaffold. See `CLAUDE.md` roadmap + `memory/project_planning_redesign.md`.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

## Role

**The lock gate.** You are the final mechanical step — no LLM re-decisions, no ambiguity, no prompts. You read all prior phase artifacts, decompose the goal_checklist into atomic R-G-R steps, call `build_locked_plan` to compute SHA256, write `plan.md` + `plan.json`, start the task + run, set task metadata markers, log `gauntlet_complete`, and hand off to the execution phase.

This skill is intentionally thin. If you find yourself reasoning about scope / architecture / failure modes — STOP. That reasoning belongs upstream. Your only creative work is atomic_steps decomposition.

## Input contract

Read `.devboard/goals/<goal_id>/`:
- `brainstorm.md` YAML frontmatter → `scope_decision` (verbatim as `scope_mode`) + `non_goals` (from deferred `req_list`)
- `gauntlet/frame.md` YAML frontmatter → `problem`, `success_definition`, `non_goals` (merge)
- `gauntlet/arch.md` YAML frontmatter → `architecture` summary, `out_of_scope_guard`, `critical_files`, `complexity.ENG_REVIEW_NEEDED`, `ui_surface`, `design_review` (if present)
- `gauntlet/challenge.md` YAML frontmatter + body → `known_failure_modes` list

Fallback: if `brainstorm.md` lacks `scope_mode` (legacy), default `scope_decision="HOLD"` and log `no_brainstorm_frontmatter` decision marker (matches current frozen gauntlet behavior).

## Output contract

1. `plan.json` — via `agentboard_lock_plan` (computes SHA256, covers `problem` / `non_goals` / `scope_decision` / `architecture` / `goal_checklist` / `atomic_steps`).
2. `plan.md` — human-readable version (written by `lock_plan` side-effect).
3. Task + run created via `agentboard_start_task`.
4. `task.metadata` set (`production_destined`, `security_sensitive_plan`, `ui_surface`).
5. `decisions.jsonl` entry `phase="lock"`, `verdict_source="LOCKED"`, reasoning=hash.
6. Checkpoint `gauntlet_complete` (or future `lock_complete`) emitted.

## Phases / Steps (TBD)

1. Load all upstream phase frontmatter (direct Read).
2. Build Decide JSON:
   - `problem`, `non_goals`, `architecture`, `known_failure_modes`, `goal_checklist`, `out_of_scope_guard` — from upstream frontmatter
   - `scope_decision` ← `brainstorm.md` frontmatter `scope_mode` (verbatim, default `HOLD`)
   - `atomic_steps` — **only creative work**: decompose each goal_checklist item into 1-assertion R-G-R cycles (~2-5 min each). Apply step splitter: any `behavior` containing "and" / "with" / multiple impl_files → split.
   - `token_ceiling`, `max_iterations` (clamp 2-10), `integration_test_command`, `borderline_decisions` (surface upstream unresolved items)
3. Step Quality Check — flag atomic_steps containing "and" / multi-file / multi-assertion; offer user split suggestions.
4. Resolve `borderline_decisions` one at a time with user.
5. Present plan for approval (`AskUserQuestion`): "Plan ready. Approve to lock? (yes / no + revise: problem|arch|challenge)". Note: `scope` is not revisable here — back to intent if needed.
6. `agentboard_approve_plan(approved=True)` → `agentboard_lock_plan(goal_id, decide_json)` → save locked_hash.
7. `agentboard_start_task` → get task_id + run_id.
8. Task metadata markers:
   - `production_destined` (default true; false only on explicit "throwaway")
   - `security_sensitive_plan` ← `agentboard_check_security_sensitive(arch_text + atomic_steps_text)`
   - `ui_surface` ← upstream `arch.md` frontmatter OR keyword scan
9. `agentboard_checkpoint("gauntlet_complete", {locked_hash, atomic_steps_count})` — rename to `lock_complete` in C-layer phase-event work.

## --deep modes

None. Lock is mechanical — depth comes from upstream phases.

## Handoff

After lock + start_task + checkpoint:

1. **Provisional Overview report (non-blocking)**: invoke `agentboard-synthesize-report` via Skill tool. Catch + log `NARRATIVE_SKIPPED` on failure; never gate handoff.
2. Read `arch.md` frontmatter `complexity.ENG_REVIEW_NEEDED`:
   - false → invoke execution phase directly (currently `agentboard-tdd`; future `agentboard-execute`).
   - true → `AskUserQuestion`: "TDD 시작 전 engineering review 실행할까요? [Y/n]"
     - Y → `agentboard-eng-review` (it invokes execution phase itself on completion)
     - n → execution phase directly

Thread `{task_id, run_id}` through all downstream calls.

## Required MCP calls

| When | Tool |
|---|---|
| Step 6 | `agentboard_approve_plan(approved=True)` + `agentboard_lock_plan(goal_id, decide_json)` |
| Step 7 | `agentboard_start_task(goal_id)` |
| Step 8 | `agentboard_check_security_sensitive(diff=<plan_text>)`, `agentboard_update_task_status(task_id, "planning", metadata={...})` |
| Step 9 | `agentboard_checkpoint(run_id, "gauntlet_complete", {...})` |
| Handoff Step 1 | Skill → `agentboard-synthesize-report` |
| Handoff Step 2 | Skill → `agentboard-eng-review` OR execution-phase skill |

## Transition note — execution phase

Currently lock hands off to `agentboard-tdd` (the frozen chain) because no D1f execution skill exists yet. Two near-term options:
1. Keep handoff to `agentboard-tdd` **with freeze-exempt flag** ("invoked via new D1 chain, not legacy route") until D1f lands.
2. Define `agentboard-execute` in a future D1f milestone (Red-Green-Refactor loop, no changes to Iron Law — just freshly structured output).

Default = option 1 until D1f ships.

## Freeze notice

Not auto-invoked until D3 cutover. This skill is the terminus of D1 planning phases; everything downstream (execute / review / approval) is unchanged for now.
