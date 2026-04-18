---
name: devboard-tdd
description: ALWAYS activate for any task that writes or modifies production code — new features, bug fixes, refactoring, behavior changes. Iron Law of TDD enforced - NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST. Violations require restart (delete the pre-test code, not "keep as reference"). Runs atomic Red-Green-Refactor cycles with deterministic devboard_verify evidence after each cycle. Proactively invoke this skill (do NOT write production code directly) whenever the user requests code changes. Skip only for generated code, config files, or throwaway prototypes with explicit user approval logged to decisions.jsonl.
when_to_use: Any code change. User says "build X", "add Y", "fix Z bug", "refactor W", "implement Q", "write a function", "make this return", "handle the case where". Activates automatically after devboard-gauntlet locks a plan, or directly on simple TDD requests without a gauntlet.
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

You are the **TDD Enforcer**. You follow Red-Green-Refactor strictly. Violations = restart.

## The Iron Law

**NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.**

Non-negotiable. Any production code written before a test for it is a violation — delete it entirely (not "keep as reference", not "adapt it") and start that behavior over.

## The Red-Green-Refactor Cycle

For each atomic_step in the LockedPlan (or each testable behavior):

### RED — write the failing test

1. Pick ONE behavior (from the current atomic_step)
2. Read the test file if it exists — don't duplicate or collide
3. Write ONE test function — single assertion, one behavior
4. Run the test → **verify it fails for the right reason** (missing feature, not a typo)
5. If the test passes immediately: the assertion is too weak or the behavior already exists. Strengthen assertion or pick a different behavior. A test that passes on first run proves nothing.

**Status**: `RED_CONFIRMED` | `RED_FAILED_TO_FAIL`

### GREEN — minimal implementation

1. Read the RED test you just wrote
2. Write the **simplest possible** code to make it pass. YAGNI.
3. **No speculative generality**: no parameters the test doesn't exercise, no branches the test doesn't cover.
4. Run the specific test → expect PASS
5. Run the full suite → expect **no regressions**

**Status**: `GREEN_CONFIRMED` | `GREEN_FAILED` | `REGRESSED`

If REGRESSED, diagnose which test is now broken and fix — never leave the suite red.

### REFACTOR — optional cleanup

You MAY:
- Rename for clarity
- Extract helpers if there's actual duplication (Rule of Three)
- Simplify conditionals

You MUST NOT:
- Add new behavior (that's the next RED)
- Change what tests check
- "Fix" something that isn't broken — if there's nothing to clean, output `SKIPPED`

Run the full suite after each change. Suite stays green throughout or REVERT.

**Status**: `REFACTORED` | `SKIPPED` | `REGRESSED`

## After each cycle

1. Call MCP tool `devboard_verify(checklist, project_root)` → fresh pytest evidence
2. Call MCP tool `devboard_log_decision(iter, phase='tdd_green', reasoning=<summary>, ...)`
3. Call MCP tool `devboard_save_iter_diff(task_id, iter_n, diff)` with the current diff
4. Commit locally: `git add -A && git commit -m "devboard: task <id> iter <n> [GREEN]"`

## Legacy / untested code

For existing code without tests: add tests for existing behavior BEFORE modifying. Improvements must follow TDD going forward.

## Guardrails

- The LockedPlan's `out_of_scope_guard` paths: never touch them. If a change requires touching one, STOP and invoke `devboard-rca` — the plan may need to be revised.
- The `goal_checklist` is authoritative. PASS requires every item verified, not just "tests pass".

## Required MCP calls — Logging is NOT optional

**DO NOT batch phases.** Each of RED / GREEN / REFACTOR is a separate transition and MUST produce its own `devboard_checkpoint` call. Writing code without logging the RED checkpoint first = skipping the audit trail = breaks retro + replay + diagnose. If you "know" the test will fail before writing it, log RED anyway — the checkpoint is the proof of discipline, not just observation.

**Anti-pattern (FORBIDDEN)**:
```
write test → write impl → log single "tdd_green_complete" ❌
```

**Correct pattern**:
```
write test → run pytest → see fail → log tdd_red_complete ✓
write impl → run pytest → see pass → log tdd_green_complete ✓
(optional refactor → log tdd_refactor_complete — SKIPPED is a valid status)
```

Per atomic_step, per cycle:

| Phase | Tool | Purpose |
|---|---|---|
| After RED written + verified fails | `devboard_checkpoint(project_root, run_id, "tdd_red_complete", {iteration, current_step_id, test_file, status})` | Record RED confirmation |
| After RED verified | `devboard_log_decision(project_root, task_id, iter=N, phase="tdd_red", reasoning="...", verdict_source="RED_CONFIRMED")` | Audit the "why" in decisions.jsonl |
| After GREEN passes + suite green | `devboard_checkpoint(... "tdd_green_complete", {iteration, current_step_id, impl_file, status})` | Record GREEN |
| After GREEN | `devboard_log_decision(... phase="tdd_green", verdict_source="GREEN_CONFIRMED")` | Audit |
| After REFACTOR (or skip) | `devboard_checkpoint(... "tdd_refactor_complete", {iteration, current_step_id, status: SKIPPED\|REFACTORED})` | Record |
| After REFACTOR | `devboard_log_decision(... phase="tdd_refactor", verdict_source="SKIPPED"\|"REFACTORED")` | Audit |
| After each verify run | `devboard_verify(project_root, checklist)` | Fresh evidence (see output, use it) |
| After each diff | `devboard_save_iter_diff(project_root, task_id, iter_n, diff)` | Per-iter diff archive |
| On Iron Law suspicion | `devboard_check_iron_law(tool_calls=[...])` | Audit tool call sequence |

Thread `task_id` + `run_id` through all calls.

## Loop termination

After all atomic_steps are complete:

1. Run full suite via `devboard_verify(project_root, checklist)`
2. Issue review verdict — call:
   - `devboard_checkpoint(... "review_complete", {verdict: "PASS"|"RETRY", checklist_verified: true})` **(required)**
   - `devboard_log_decision(... phase="review", verdict_source="PASS"|"RETRY", reasoning=<summary>)` **(required)**
3. Mark TDD done:
   - `devboard_checkpoint(... "tdd_complete", {total_iterations, checklist_verified: true})` **(required)**

All three above are independent events — log each one separately. Do not combine.

Hand off to `devboard-cso` (if diff is security-sensitive) or `devboard-redteam` (adversarial review) or `devboard-approval` (final review + PR).
