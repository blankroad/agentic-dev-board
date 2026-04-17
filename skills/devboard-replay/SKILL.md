---
name: devboard-replay
description: Time-travel — branch a past run from a specific iteration and re-execute with a variant strategy. Preserves the original run untouched; new run gets its own run_id and checkpoint trail.
when_to_use: User wants to "try a different approach from iteration N", "what if we'd done X instead", or regression-test a past bug by replaying its pre-fix state. Also useful after an RCA-escalated goal to try a fresh approach from an earlier checkpoint.
---

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
- Hand off to `devboard-tdd` at iteration N+1 with:
  - LockedPlan unchanged
  - Fresh convergence/blocked flags
  - `variant_note` as a planning hint

The TDD skill resumes RED-GREEN-REFACTOR from that point with the variant influence.

## Step 4 — Audit

Both runs (original and replay) coexist in `.devboard/runs/`:
- Original: `run_abc.jsonl`
- Replay: `replay_xyz.jsonl` (starts with `replay_start` event)

Retro reports surface both — variants become material for retrospective pattern analysis.

## Discipline

- **Do NOT modify the source run** — replay creates a branch, never overwrites
- **LockedPlan is still authoritative** — even variants can't touch `out_of_scope_guard` paths
- **Variant note is logged** — future retros can see why this path was explored
