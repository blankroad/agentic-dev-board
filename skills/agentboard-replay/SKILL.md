---
name: agentboard-replay
description: Time-travel — branch a past run from iteration N with a variant strategy. Invoke when the user says "replay", "try different approach from iteration N", "what if we'd done X instead", "branch from checkpoint", "regression-test this past state", "go back to when X worked", or "explore alternative from iter N". Preserves the original run untouched; new run gets its own run_id and checkpoint trail. LockedPlan is still authoritative (out_of_scope_guard paths still cannot be touched). Useful after agentboard-rca escalates (3 consecutive failures → rethink) to explore a different branch from an earlier checkpoint without losing the failed trail.
when_to_use: User explicitly asks for replay, variant exploration, time-travel, or branching from a past checkpoint. Also proactively suggest after agentboard-rca escalation, or when the user is debating "what if we'd taken approach X" for a completed run.
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

## Preamble — Project Guard (MANDATORY first check)

Before any other action, verify devboard is initialized in this project. Run this Bash command:

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

- Output `MISSING` → print this message to the user and **exit the skill immediately** (do NOT call any MCP tools, do NOT proceed with any steps below):
  > devboard is not initialized in this project. Run `devboard init && devboard install` first to enable this skill.
- Output `OK` → proceed with the skill below.

You are the **Time-travel Replay Agent**. You re-execute runs from past checkpoints with variants.

## Step 1 — Identify source run

Ask user:
- Which run? (call `devboard_list_runs()` → show id/goal/last_iteration/converged)
- From which iteration? (iter 1, 2, ..., N)
- What variant? ("try async instead", "use different library", free-form annotation)

## Step 2 — Branch

Call MCP tool:
```
devboard_replay(
  source_run_id="run_abc",
  from_iteration=2,
  variant_note="try async instead of threads"
)
```

Returns:
- `new_run_id` (e.g., "replay_xyz")
- `initial_state` — the graph state at iter N+1, with `converged=False`, `blocked=False`, fresh reflect_json

The new run file at `.devboard/runs/<new_run_id>.jsonl` starts with a `replay_start` event recording:
- Source run id
- From iteration
- Variant note
- Branched state snapshot (for audit)

## Step 3 — Create task and re-execute

- Create a new Task linked to the original goal (e.g., title: `[replay] <original>`)
- Load the original LockedPlan (unchanged — atomic_steps and out_of_scope_guard still apply)
- Inject the variant note into the next planner call as `previous_strategy`
- Hand off to `agentboard-tdd` at iteration N+1 with:
  - LockedPlan unchanged
  - Fresh convergence/blocked flags
  - `variant_note` as a planning hint

The TDD skill resumes RED-GREEN-REFACTOR from that point with the variant influence.

## Step 4 — Audit

Both runs (original and replay) coexist in `.devboard/runs/`:
- Original: `run_abc.jsonl`
- Replay: `replay_xyz.jsonl` (starts with `replay_start` event)

Retro reports surface both — variants become material for retrospective pattern analysis.

## Required MCP calls

| When | Tool |
|---|---|
| Discovery | `devboard_list_runs(project_root)` — show user the candidate runs |
| Branch | `devboard_replay(project_root, source_run_id, from_iteration, variant_note)` — creates new run_id + initial state |
| New task | `devboard_start_task(project_root, goal_id, title="[replay] <original>")` — independent task for the variant |
| Resume point | `devboard_checkpoint(project_root, new_run_id, "replay_resumed", {from_iteration, variant_note})` |

Then hand off to `agentboard-tdd` with the new `{task_id, run_id}` and `variant_note` as the initial `previous_strategy`.

## Discipline

- **Do NOT modify the source run** — replay creates a branch, never overwrites
- **LockedPlan is still authoritative** — even variants can't touch `out_of_scope_guard` paths
- **Variant note is logged** — future retros can see why this path was explored
