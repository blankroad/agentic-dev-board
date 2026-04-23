---
name: agentboard-execute
description: D1f (2026-04-23). Execution phase of the D1 chain — replaces agentboard-tdd as the default post-lock TDD loop. Iron Law of TDD enforced (NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST). Runs atomic Red-Green-Refactor cycles with deterministic agentboard_verify evidence. Entry point reads {task_id, run_id, locked_hash} from the preceding agentboard-lock handoff. Emits phase_start / phase_end events per the P4 Observable-by-Default principle. Not auto-invoked pre-cutover — activated by agentboard-lock's handoff OR explicit user invocation.
when_to_use: Invoked automatically by agentboard-lock after the LockedPlan is written and task + run are started. Pre-cutover, also accepts explicit user invocation ("run execute on task X", "tdd this"). After D3 cutover, replaces agentboard-tdd for default routing.
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

> **Status (2026-04-23, D1f CONTENT v1):** Direct port of `agentboard-tdd` into the D1 chain with three substantive additions: (1) phase_start / phase_end events per decisions.jsonl per Core Principle P4, (2) entry-point contract reading from agentboard-lock's handoff payload, (3) handoff name refresh — the default execution-phase transition for the new chain. Parallel with legacy `agentboard-tdd` until D3 cutover; legacy stays routed during the freeze window.

## Preamble — Project Guard (MANDATORY first check)

Before any other action, verify agentboard is initialized in this project. Run this Bash command:

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
```

- Output `MISSING` → print this message to the user and **exit the skill immediately** (do NOT call any MCP tools, do NOT proceed with any steps below):
  > agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill.
- Output `OK` → proceed with the skill below.

You are the **Execution Enforcer**. You follow Red-Green-Refactor strictly. Violations = restart.

## D1 chain entry (MANDATORY before first RED)

This skill is the execution phase of the D1 planning chain. Its inputs are the handoff payload from `agentboard-lock`:

- `task_id` — from `agentboard_start_task` in lock Step 5
- `run_id` — same
- `locked_hash` — from `agentboard_lock_plan` in lock Step 4
- `goal_id` — threads through

### Step 0 — Phase start event (P4)

Emit a phase-boundary event to `decisions.jsonl` so fleet observability (TUI phases tab, retro) can see where every agent is:

```
agentboard_log_decision(
    project_root, task_id,
    iter=0,
    phase="execute",
    reasoning=f"phase_start — locked_hash={locked_hash}, atomic_steps={N}",
    verdict_source="PHASE_START",
)
```

### Step 0 — Plan load

Call `agentboard_load_plan(project_root, goal_id)` to load the LockedPlan. Extract:
- `atomic_steps` (the sequence of R-G-R behaviors to execute)
- `goal_checklist` (the authoritative PASS/FAIL criteria at loop end)
- `out_of_scope_guard` (paths iron_law hook blocks)
- `integration_test_command` (smoke command used by approval later)

If the load fails or `locked_hash` received from lock doesn't match plan.json's hash: STOP. Emit `agentboard_log_decision(phase="execute", verdict_source="HASH_MISMATCH_ABORT")` and exit. Hash mismatch means a non-lock path wrote plan.json and the contract is broken.

## Learnings Preamble (MANDATORY before first RED)

Before writing any test, harvest the **Preemptive Defense Checklist** from past sessions. The point is simple: red-team has already taught this project what categories of bug we keep shipping (binary input crashes, compose-once state sync, cached stale state, real-TTY vs Pilot divergence, etc.). If those lessons aren't in your working context at RED time, you will rebuild the same bugs and burn 2–4 red-team rounds you could have skipped.

### Step 1 — Two-stage lookup

Call these MCP tools in order (they already exist — do not wrap, do not reimplement):

1. **Primary (semantic match on current task)**:
   ```
   agentboard_relevant_learnings(project_root, goal_description="<goal title + short arch summary>")
   ```
   Returns learnings ranked by relevance to the task's natural-language description.

2. **Secondary (tag-based broad sweep)**:
   ```
   agentboard_search_learnings(project_root, tag="<tech_tag>")
   ```
   Where `<tech_tag>` is chosen from the task's domain — e.g. `"textual"` / `"tui"` / `"mcp"` / `"storage"` / `"async"`. Run once per domain involved.

Union the two result sets. Over-match is safe (false positives are cheap to ignore at RED time). Under-match is expensive (false negatives become tomorrow's redteam BROKEN).

### Step 2 — Build the Preemptive Defense Checklist

Cap the review at **top N=5** learnings by `confidence` (descending). For each, read ONLY `name`, `tags`, and the first **200자** (approx. 200 chars) of `content` — do not dump full bodies into context. If you need deeper detail later, re-fetch by name.

Produce a structured checklist like this (plain text or JSON, whichever flows in your session):

```
Preemptive Defense Checklist
  1. category: widget-lifecycle
     learning: widgets-need-reactive-hook-not-compose-once
     check:    after state mutation, does each pane have a refresh path?
     atomic_steps_tag: ui, widget

  2. category: io-safety
     learning: read-text-in-compose-must-catch-unicode
     check:    is every Path.read_text() wrapped in try/(OSError, UnicodeDecodeError)?
     atomic_steps_tag: io, file

  ... (up to 5 entries)
```

### Step 3 — Reference in each atomic_step RED test

When writing a RED test whose behavior maps to a checklist entry, **annotate the test with a `# guards: <learning-name>` comment** (one tag per applicable learning). Example:

```python
def test_plan_file_binary_does_not_crash_mount() -> None:
    # guards: read-text-in-compose-must-catch-unicode
    ...
```

This produces an externally observable artifact proving the checklist was consulted, not just generated. If an atomic_step has no applicable checklist entry, no tag is required — do not fabricate coverage.

### Step 4 — Empty-learnings fallback

If both lookups return zero results (new project / first task):

```
No prior learnings — proceed with default TDD.
```

Print that one line, skip the checklist, and proceed to the normal RED-GREEN-REFACTOR loop below.

### Why this exists

Past observation (TUI v2.0 = 4 red-team rounds, v2.1 = 3 red-team rounds) showed Claude reliably reinventing the same crash categories: binary input, compose-once staleness, real-TTY vs Pilot divergence, cached stale state. These categories are already captured in `.agentboard/learnings/*.md`. The Preamble makes sure they show up on the next RED, not on the next BROKEN.

## The Iron Law

**NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.**

Non-negotiable. Any production code written before a test for it is a violation — delete it entirely (not "keep as reference", not "adapt it") and start that behavior over.

## The Red-Green-Refactor Cycle

For each atomic_step in the LockedPlan:

### RED — write the failing test

1. Pick ONE behavior (the current atomic_step).
2. Read the test file if it exists — don't duplicate or collide.
3. Write ONE test function — single assertion, one behavior.
4. Run the test → **verify it fails for the right reason** (missing feature, not a typo).
5. If the test passes immediately: the assertion is too weak or the behavior already exists. Strengthen assertion or pick a different behavior. A test that passes on first run proves nothing.

**Status**: `RED_CONFIRMED` | `RED_FAILED_TO_FAIL`

#### Edge-Case RED Rule

When the Preemptive Defense Checklist contains an entry whose category matches the current `atomic_step` behavior, the RED test MUST assert the **happy path + at least 1 edge case** — not only the happy path. This is what turns learnings from "notes I read" into "tests that run".

**Initial edge-case categories (extend as learnings accumulate):**

1. **empty / None input** — functions that accept a string / list / dict must survive `""`, `None`, `[]`, `{}` without crashing; verify fallback behavior.
2. **binary / non-UTF-8 file** — any `Path.read_text()` in a mount / compose / CLI-entry path must tolerate invalid bytes (matches `read-text-in-compose-must-catch-unicode`).
3. **concurrent mutation** — when state is mutated mid-iteration (e.g. `runs_dir.glob()` then `p.stat()`), the consumer must not raise on TOCTOU races.
4. **cached stale** — `cached_property` / `functools.cache` / widget compose-once values must either invalidate on state change OR expose a refresh hook; clobbers happen when a setter updates the upstream source but readers still see cached value.
5. **integration wiring** — widgets / workers instantiated in isolation pass unit tests but the App may not actually wire them up; test the Pilot-driven end-to-end wiring at least once per feature.
6. **real-TTY divergence** — Textual Pilot rendering differs from a real terminal (border height, focus chain, input visibility). For TUI tasks, at least one test or manual TTY check must exercise the real pty path.

**happy + 1 edge pattern (example)**:

```python
def test_plan_markdown_renders_plan_md(tmp_path):
    # happy path
    ...

def test_plan_markdown_tolerates_binary_plan_md(tmp_path):
    # guards: read-text-in-compose-must-catch-unicode
    # edge: binary / non-UTF-8 file category
    (tmp_path / "plan.md").write_bytes(b"\xff\xfe\x00")
    ...
```

**Naming convention (externally observable proof)**: when an edge test maps to a category, encode the category in the **test function name** (e.g. `_with_empty_input`, `_tolerates_binary_*`, `_stale_cache_*`, `_real_tty_*`) OR in the test **docstring** (first line names the category). This lets a reviewer — or the red-team skill — grep the suite for edge coverage without running anything.

**YAGNI — is this speculative testing?** No. YAGNI forbids defending against *hypothetical future* failure modes. These categories are *already documented* in `.agentboard/learnings/*.md` as **known-risk** attack vectors that red-team has shipped multiple times. A test that defends a known-risk category is not speculation — it's regression guarding a recurring class of bug.

If the current `atomic_step` behavior has no matching category in the checklist (or the checklist is empty for a new project), the standard single-assertion RED is fine — do NOT invent categories to pad the test. Matching is intentional, not obligatory.

### GREEN — minimal implementation

1. Read the RED test you just wrote.
2. Write the **simplest possible** code to make it pass. YAGNI.
3. **No speculative generality**: no parameters the test doesn't exercise, no branches the test doesn't cover.
4. Run the specific test → expect PASS.
5. Run the full suite → expect **no regressions**.

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

1. Call MCP tool `agentboard_verify(project_root, checklist)` → fresh pytest evidence.
2. Call MCP tool `agentboard_log_decision(task_id, iter=N, phase='tdd_green', reasoning=<summary>, verdict_source='GREEN_CONFIRMED')`.
3. Call MCP tool `agentboard_save_iter_diff(project_root, task_id, iter_n, diff)` with the current diff.
4. Commit locally: `git add -A && git commit -m "agentboard: task <id> iter <n> [GREEN]"`.

The phase name in `log_decision` stays `tdd_red` / `tdd_green` / `tdd_refactor` for retro backward-compat (legacy `agentboard-tdd` logs used the same names). The `phase="execute"` phase_start / phase_end events are separate — they mark the D1-chain transition, not per-cycle TDD phases.

## Legacy / untested code

For existing code without tests: add tests for existing behavior BEFORE modifying. Improvements must follow TDD going forward.

## Guardrails

- The LockedPlan's `out_of_scope_guard` paths: never touch them. If a change requires touching one, STOP and invoke `agentboard-rca` — the plan may need to be revised.
- The `goal_checklist` is authoritative. PASS requires every item verified, not just "tests pass".
- `locked_hash` mismatch at any point → abort. The plan is immutable by contract.

## Required MCP calls — Logging is NOT optional

**DO NOT batch phases.** Each of RED / GREEN / REFACTOR is a separate transition and MUST produce its own `agentboard_checkpoint` call. Writing code without logging the RED checkpoint first = skipping the audit trail = breaks retro + replay + diagnose. If you "know" the test will fail before writing it, log RED anyway — the checkpoint is the proof of discipline, not just observation.

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

### Per atomic_step, per cycle

| Phase | Tool | Purpose |
|---|---|---|
| After RED written + verified fails | `agentboard_checkpoint(project_root, run_id, "tdd_red_complete", {iteration, current_step_id, test_file, status})` | Record RED confirmation |
| After RED verified | `agentboard_log_decision(project_root, task_id, iter=N, phase="tdd_red", reasoning="...", verdict_source="RED_CONFIRMED")` | Audit the "why" |
| After GREEN passes + suite green | `agentboard_checkpoint(... "tdd_green_complete", {iteration, current_step_id, impl_file, status})` | Record GREEN |
| After GREEN | `agentboard_log_decision(... phase="tdd_green", verdict_source="GREEN_CONFIRMED")` | Audit |
| After REFACTOR (or skip) | `agentboard_checkpoint(... "tdd_refactor_complete", {iteration, current_step_id, status: SKIPPED\|REFACTORED})` | Record |
| After REFACTOR | `agentboard_log_decision(... phase="tdd_refactor", verdict_source="SKIPPED"\|"REFACTORED")` | Audit |
| After each verify run | `agentboard_verify(project_root, checklist)` | Fresh evidence |
| After each diff | `agentboard_save_iter_diff(project_root, task_id, iter_n, diff)` | Per-iter diff archive |
| On Iron Law suspicion | `agentboard_check_iron_law(tool_calls=[...])` | Audit tool call sequence |

### Phase-boundary events (D1 additions, P4 Observable-by-Default)

| When | Tool | Notes |
|---|---|---|
| On entry (before first RED) | `agentboard_log_decision(phase="execute", iter=0, verdict_source="PHASE_START", reasoning="locked_hash=<hash>, atomic_steps=<N>")` | Fleet observability marker |
| On normal exit (after loop termination) | `agentboard_log_decision(phase="execute", iter=N, verdict_source="PHASE_END", reasoning="<total iters + checklist verdict>")` | Fleet observability marker |
| On abort (hash mismatch, blocked, etc.) | `agentboard_log_decision(phase="execute", iter=N, verdict_source="PHASE_ABORT", reasoning="<reason>")` | Error visibility |

Thread `task_id` + `run_id` through all calls.

## Loop termination

After all atomic_steps are complete:

1. Run full suite via `agentboard_verify(project_root, checklist)`.
2. Issue review verdict — call:
   - `agentboard_checkpoint(... "review_complete", {verdict: "PASS"|"RETRY", checklist_verified: true})` **(required)**
   - `agentboard_log_decision(... phase="review", verdict_source="PASS"|"RETRY", reasoning=<summary>)` **(required)**
3. Mark execution done:
   - `agentboard_checkpoint(... "tdd_complete", {total_iterations, checklist_verified: true})` **(required, event name retained for retro compat)**
4. Emit phase_end event:
   - `agentboard_log_decision(phase="execute", verdict_source="PHASE_END", reasoning="<total iters>, review={PASS|RETRY}")`

All four above are independent events — log each one separately. Do not combine.

### Handoff

Hand off to `agentboard-parallel-review` (preferred — dispatches CSO + redteam in parallel via the Agent tool and logs a single `phase="parallel_review"` entry). `agentboard-parallel-review` auto-skips either side per `task.metadata.security_sensitive_plan` / `production_destined`, so it handles the "CSO-only" and "redteam-only" cases internally. The legacy sequential path (`agentboard-cso` → `agentboard-redteam` → `agentboard-approval`) is still accepted by `agentboard-approval` as a backward-compat fallback when no `phase="parallel_review"` entry is present.

**Parallel-review is NOT part of the frozen chain.** It was always a standalone dispatcher and is explicitly sanctioned for D1 handoff use. The freeze applies to `agentboard-gauntlet` / `agentboard-tdd` / `agentboard-approval` as the planning→execution→merge routing default. Execute handing off to parallel-review is the correct flow.

---

## UI Preview integration (when ui_surface=True)

After the FIRST atomic_step that mounts a user-visible widget turns GREEN — AND `task.metadata.ui_surface == True` — invoke `agentboard-ui-preview` via the Skill tool with `layer=1`. The skill captures a Layer 1 plain-text snapshot via `agentboard_tui_capture_snapshot`, saves it under `.agentboard/tui_snapshots/<goal_id>/layer1/<scene_id>.txt`, and diffs against the Layer 0 mockup recorded in arch.md.

- Drift detected → surface diff to user and ask whether to continue execute or branch to `agentboard-rca`.
- No drift → resume the Red-Green-Refactor loop with the next atomic_step.

Optional re-run: after any subsequent step that visibly mutates UI state, call ui-preview Layer 1 again so the user sees incremental changes mid-loop instead of only at approval.

Skip entirely when `ui_surface=False`.

---

## `--deep` modes

**None.** Execution is mechanical — Iron Law + R-G-R discipline + out_of_scope_guard enforcement. Depth during planning lives upstream in intent / architecture / stress. Adding a `--deep` flag here would mean "bigger test suite / more rigorous checklist verification", which are already the defaults and not opt-in.

If future experience calls for it, candidates:
- `--deep=mutation` — run `mutmut` or `cosmic-ray` after each GREEN to verify test quality.
- `--deep=property` — require at least one hypothesis-based property test per atomic_step.

Deferred — not needed at D1f.

---

## Design notes (why this structure)

- **This is a rename + P4 events + D1 entry point.** The Iron Law, R-G-R rhythm, Learnings Preamble, and per-cycle MCP logging are all verbatim from legacy `agentboard-tdd` — porting those patterns unchanged is deliberate. The D1 goal is structural reorganization, not behavioral rewrite of the execution discipline.
- **Phase name `execute` is used only for phase_start / phase_end events.** Per-cycle `tdd_red` / `tdd_green` / `tdd_refactor` phase names are retained for retro compat — existing dashboards and queries expect them.
- **`locked_hash` verification at entry.** The LockedPlan is immutable by F4 contract; if a concurrent writer has modified it since lock, the execution phase is running against stale intent. Fail fast.
- **Handoff to parallel-review is unchanged.** Parallel-review was never part of the frozen chain — it's a dispatcher. Execute → parallel-review is the correct flow post-D3 cutover too.
- **No `--deep` modes by design.** Execution is where discipline matters, not depth. Depth is an intent/architecture concern.

---

## Freeze notice

Default skill routing still auto-activates `agentboard-tdd` on code-change requests during the freeze window. `agentboard-execute` runs only when explicitly invoked OR when `agentboard-lock` hands off via the D1 chain. D3 cutover flips the default: `agentboard-tdd` is deprecated, this skill becomes the canonical execution phase, and the freeze lifts. See `memory/feedback_freeze_gauntlet_flow.md`.
