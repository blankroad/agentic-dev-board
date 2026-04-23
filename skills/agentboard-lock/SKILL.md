---
name: agentboard-lock
description: D1e (2026-04-23). Terminal phase of the D1 chain. Mechanical synthesis — reads all prior phase frontmatter (brainstorm / frame / arch / challenge), decomposes goal_checklist into atomic R-G-R steps (the ONLY creative work), calls build_locked_plan to compute SHA256, writes plan.md + plan.json, starts task + run, sets metadata markers, logs gauntlet_complete checkpoint, invokes synthesize-report (non-blocking), hands off to execution phase. NO LLM re-decisions — scope_decision is injected from brainstorm.md verbatim. Not auto-invoked pre-cutover.
when_to_use: After agentboard-stress completes (+ any replan loops settled). Auto-invoked by stress at Step 5 handoff. Pre-cutover, invoke only when explicitly asked.
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

> **Status (2026-04-23, D1e CONTENT v1):** Ported from the legacy `agentboard-gauntlet` Step 5 Decide + Finalize + Handoff. Terminal phase of the D1 chain. Preserves F4 invariant: `scope_decision` is read verbatim from `brainstorm.md` frontmatter, never re-derived. Parallel with the frozen gauntlet chain until D3 cutover.

You are the **Lock Gate** — the final mechanical step of the D1 planning chain. No LLM re-decisions, no ambiguity, no scope prompts. You read all prior phase artifacts, decompose `goal_checklist` into atomic Red-Green-Refactor steps (the only creative work), compute SHA256 via `build_locked_plan`, write `plan.md` + `plan.json`, start the task + run, set task metadata markers, log `gauntlet_complete`, and hand off.

**Discipline reminder**: if you find yourself reasoning about scope / architecture / failure modes at this step — STOP. That work belongs upstream. If any field is missing or wrong, route back to the owning phase via AskUserQuestion. Do NOT patch over ambiguity here.

## Step 0 — Preamble (project guard + upstream load)

### Project guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

### Load upstream (all 4 phases required)

Read and parse YAML frontmatter:

- `.devboard/goals/<goal_id>/brainstorm.md` — `scope_mode`, `refined_goal`, `req_list`, `rationale`, `alternatives_considered`
- `.devboard/goals/<goal_id>/gauntlet/frame.md` — `problem`, `wedge`, `non_goals`, `success_definition`, `key_assumptions`, `riskiest_assumption`
- `.devboard/goals/<goal_id>/gauntlet/arch.md` — `architecture_overview`, `critical_files`, `edge_cases`, `test_strategy`, `critical_path`, `out_of_scope_guard`, `complexity`, `ui_surface`, `design_review` (if present)
- `.devboard/goals/<goal_id>/gauntlet/challenge.md` — failure modes list with severities, `warrants_replan` (should be `false` by the time you get here; if `true`, stress mis-handled the routing — `AskUserQuestion` and route back)

### Legacy fallback for missing frontmatter

If any file lacks YAML frontmatter (pre-F4 legacy goal):

1. Emit `agentboard_log_decision(phase="lock", verdict_source="LEGACY_FALLBACK", reasoning="<which file + what default applied>")`.
2. Default missing fields:
   - `scope_decision = "HOLD"` (from missing `brainstorm.md` frontmatter)
   - `non_goals = []` if frame.md missing
   - `architecture = "<free-form body>"` if arch.md has no frontmatter
3. Continue — legacy goals still lockable with reduced fidelity.

---

## Step 1 — Build Decide JSON (mechanical, no re-decisions)

Map upstream frontmatter fields directly into the LockedPlan schema. This is a lookup table, not reasoning:

```python
decide_json = {
    "problem":                 frame.problem,
    "non_goals":               frame.non_goals + <req_list deferred items>,
    "scope_decision":          brainstorm.scope_mode,             # VERBATIM. Default HOLD only on legacy.
    "architecture":            arch.architecture_overview,
    "known_failure_modes":     [f"{sev}: {name}" for failure_mode in challenge.failure_modes],
    "goal_checklist":          frame.success_definition,          # these are the "done" conditions
    "out_of_scope_guard":      arch.out_of_scope_guard,
    "atomic_steps":            <Step 2 decomposition — only creative work>,
    "token_ceiling":           <estimate — default 100_000, bump to 200_000 for ≥10 atomic_steps>,
    "max_iterations":          <clamp: max(2, min(10, len(atomic_steps) // 2 + 3))>,
    "integration_test_command": <"pytest -x" for Python projects; user override respected>,
    "borderline_decisions":    <surface any unresolved items from upstream phases>,
}
```

### Invariant

**`scope_decision` must match `brainstorm.scope_mode` character-for-character** (legacy fallback default = `HOLD`). If you find yourself picking a different value — STOP. That's an F4 regression.

---

## Step 2 — `atomic_steps` decomposition (the ONLY creative work)

Break `goal_checklist` (= `frame.success_definition`) into atomic R-G-R cycles. Each step:

- **~2-5 min work** — one Red-Green-Refactor cycle
- **One assertion, one behavior** — NOT "implement add/sub/mul/div" but four separate steps
- **Order matters** — earlier steps are prerequisites for later
- **Error paths are distinct steps** — "div(a, 0) raises ZeroDivisionError" is its own step

### Step splitter triggers

If a `behavior` candidate contains:
- "and" — split on the "and"
- "with" — split on the "with"
- References multiple `impl_file` paths — split per file

These are heuristics; use judgment for behaviors genuinely atomic despite containing those words.

### Format

```yaml
atomic_steps:
  - id: s_001
    behavior: "ONE testable behavior (2-5 min of work)"
    test_file: "tests/test_X.py"
    test_name: "test_Y"
    impl_file: "src/agentboard/X.py"  # or "" for doc-only steps
    expected_fail_reason: "NameError: Y not defined"
```

### Doc-only steps (SKILL.md / CLAUDE.md edits)

Prompt/doc edits have no pytest test. Iron Law is N/A for these — mark:

```yaml
  - id: s_017
    behavior: "CLAUDE.md Known deferred issues updated to reflect X"
    test_file: ""
    test_name: ""
    impl_file: "CLAUDE.md"
    expected_fail_reason: "N/A — documentation/spec edit; no pytest coverage applicable"
```

### Step Quality Check (before Step 3)

Self-review each step:

```
✅ s_001: one behavior, one assertion, ≤5 min work
⚠️ s_003: behavior contains "and" — may cover 2 behaviors
    Suggestion: split into s_003a / s_003b
✅ s_004: OK
```

If all pass: silent. If any warnings: output the flagged steps + split suggestions and `AskUserQuestion`: "Adjust these steps or proceed to lock as-is?" — wait for user pick.

Bad splitting example from legacy:

```
❌ Bad: s_001 "implement auth flow with login, logout, and session validation"
  (3 behaviors; 3 assertions; GREEN impl grows too large)

✅ Good:
  s_001: "POST /auth/login with valid creds returns 200 + token"
  s_002: "POST /auth/logout invalidates the session token"
  s_003: "GET /api/protected with expired token returns 401"
```

---

## Step 3 — Resolve borderline_decisions + get plan approval

If upstream phases surfaced any `borderline_decisions` (e.g., unresolved scope tension that didn't warrant a full replan), resolve them one at a time with `AskUserQuestion` offering A/B + your recommendation.

Present the full plan summary for final review:

```
## Plan ready for lock

scope_decision: {EXPAND|SELECTIVE|HOLD|REDUCE} (from brainstorm.md)
refined_goal: {refined_goal}
wedge: {wedge}
goal_checklist: {N items}
atomic_steps: {N items}
known_failure_modes: CRITICAL {N} / HIGH {N} / MEDIUM {N}
out_of_scope_guard: {N paths}
ui_surface: {bool}
complexity.ENG_REVIEW_NEEDED: {bool}

Approve to lock? (yes / no + revise: problem|arch|challenge)
```

**Note**: `scope` is NOT revisable at this gate. If the user wants to change scope, they return to `agentboard-intent` — route: log `verdict_source="SCOPE_REVISIT_AT_LOCK"` and invoke `agentboard-intent`. Do NOT try to patch `scope_decision` here.

If user picks `no + problem` / `no + arch` / `no + challenge`: exit and invoke the corresponding upstream skill. Do NOT proceed to Step 4.

If `yes`: continue.

---

## Step 4 — Lock the plan

Call:

```
agentboard_approve_plan(project_root, goal_id, approved=True, notes=<summary>)
```

Then:

```
result = agentboard_lock_plan(project_root, goal_id, decide_json)
# Returns: {locked_hash, plan_path, goal_checklist_count, atomic_steps_count, warnings}
```

Save `locked_hash` — thread it through downstream calls.

`lock_plan` verifies `plan_review.json` status=approved (returns error if missing or revision_pending), computes SHA256 over `(problem, non_goals, scope_decision, architecture, goal_checklist, atomic_steps)`, writes `plan.md` (human-readable) + `plan.json` (machine-readable).

The plan is now **immutable**. Implementation must follow it. Any drift triggers a `rethink`.

---

## Step 5 — Start task + run

Call:

```
{task_id, run_id} = agentboard_start_task(project_root, goal_id, title=<goal.title>)
```

**SAVE BOTH** — thread through every subsequent MCP call in this session. They're the audit trail keys.

---

## Step 6 — Task metadata markers (MANDATORY)

Three markers so downstream skills (cso / redteam / approval) can decide entry deterministically. Set them right after `start_task`:

### 6.1 `production_destined`

Default `true`. Only `false` if the user explicitly said "throwaway" or "prototype" in intent phase (check `brainstorm.md` prose for the word). When in doubt, `true` — production defaults are safer.

### 6.2 `security_sensitive_plan`

Call:

```
result = agentboard_check_security_sensitive(diff=<arch.architecture_overview + atomic_steps concatenated text>)
security_sensitive_plan = result.sensitive   # boolean
```

Use returned value verbatim.

### 6.3 `ui_surface`

Use `arch.md` frontmatter `ui_surface` field if present (set by architecture Step 9's keyword scan with out-of-scope-guard exclusion). If `arch.md` has no `ui_surface` field (legacy), re-run the scan here:

- Concatenate `arch.md` body + `decide_json` text
- Case-insensitive keyword match on `tui | textual | widget | pilot | browser | ui | frontend`
- EXCLUDE matches that appear only in `out_of_scope_guard` (F4 false-positive lesson)

Record the override reason if your detection differs from arch.md:

```json
{
  "ui_surface": false,
  "ui_surface_override_reason": "arch.md contains 'tui' keyword only inside out-of-scope guard; no actual UI work."
}
```

### Call

```
agentboard_update_task_status(
    project_root, task_id, status="planning",
    metadata={
        "production_destined": <bool>,
        "security_sensitive_plan": <bool>,
        "ui_surface": <bool>,
        "ui_surface_override_reason": <str>,  # only if manually overridden
    }
)
```

Downstream skills read these:
- `agentboard-cso` — auto-skip if `security_sensitive_plan=false` AND runtime diff scan = false
- `agentboard-redteam` — auto-skip if `production_destined=false`
- `agentboard-approval` — Step 4.6 captures real-TTY smoke iff `ui_surface=true`

---

## Step 7 — Checkpoint gauntlet_complete

```
agentboard_checkpoint(
    project_root, run_id, "gauntlet_complete",
    {
        locked_hash,
        atomic_steps_count,
        goal_checklist_count,
        scope_decision,
        complexity_case: <1 or 2>,   # from arch.md complexity block
        eng_review_needed: <bool>,
        ui_surface: <bool>,
        security_sensitive: <bool>,
    }
)
```

The event name `gauntlet_complete` is retained for backward compat with retro / replay / diagnose queries. At C-layer phase-events work, this will be renamed to `lock_complete` and pair with `phase_start` / `phase_end` entries.

---

## Step 8 — Provisional Overview report (non-blocking)

Invoke `agentboard-synthesize-report` via the `Skill` tool so the TUI Overview tab renders release-notes content before any execution cycle runs:

```
try:
    Skill(agentboard-synthesize-report, "goal_id=<goal_id> task_id=<task_id>")
except Exception as exc:
    agentboard_log_decision(
        phase="lock",
        reasoning=f"synthesize-report skipped: {exc!r}",
        verdict_source="NARRATIVE_SKIPPED",
    )
```

Non-blocking by contract — failure here MUST NOT gate handoff.

---

## Step 9 — Handoff to execution

Read `arch.md` frontmatter `complexity.ENG_REVIEW_NEEDED`:

- **false** → invoke execution phase directly. Until `agentboard-execute` (future D1f) lands, that means invoking `agentboard-tdd` (legacy, frozen chain). This is the sanctioned freeze exemption — `agentboard-tdd` called via the new D1 lock handoff, not via legacy gauntlet auto-routing. Log `verdict_source="EXECUTE_VIA_LEGACY_TDD"` to mark the transition context for retro.
- **true** → `AskUserQuestion`:

  ```
  이 계획은 새 파일 {NEW_COUNT}개 + 새 abstraction {NEW_ABSTRACTIONS}개를 포함합니다.
  TDD 시작 전 engineering review를 실행할까요? (권장) [Y/n]
  ```

  - `Y` → invoke `agentboard-eng-review` via `Skill` tool. After eng-review completes, it invokes execution phase itself.
  - `n` → invoke execution phase directly. Log `verdict_source="ENG_REVIEW_DECLINED"`.

### `task_id` + `run_id` threading

Pass `{task_id, run_id, locked_hash}` through the `args` payload of the execution-phase Skill invocation so the execution skill can thread them into its own MCP calls.

### Final output

```
## D1 Lock 완료

locked_hash: {hash}
plan.md: .devboard/goals/{goal_id}/plan.md
atomic_steps: {N}
task_id: {id}
run_id: {id}
scope_decision: {mode} (from brainstorm.md)

다음 단계: {agentboard-eng-review | agentboard-tdd (legacy via D1 handoff)}
```

---

## `--deep` modes

**None.** Lock is mechanical — depth comes from upstream phases. Adding depth modes here would reintroduce LLM re-decision at the lock step, which is the very anti-pattern this skill was designed to prevent.

---

## Required MCP calls (in order, all MANDATORY)

| Step | Tool | Purpose |
|---|---|---|
| 0 | (direct `Read` on all 4 phase .md files) | Load upstream |
| 0 | `agentboard_log_decision(phase="lock", verdict_source="LEGACY_FALLBACK")` | Only if any file lacks frontmatter |
| 3 | `AskUserQuestion` | Resolve borderline_decisions + final approval |
| 4 | `agentboard_approve_plan(approved=True)` | Record approval |
| 4 | `agentboard_lock_plan(goal_id, decide_json)` | SHA256 hash + plan.md + plan.json |
| 5 | `agentboard_start_task(goal_id, title=...)` | Returns {task_id, run_id} |
| 6.2 | `agentboard_check_security_sensitive(diff=...)` | Feeds metadata marker |
| 6 | `agentboard_update_task_status(task_id, "planning", metadata={...})` | Set 3 markers |
| 7 | `agentboard_checkpoint(run_id, "gauntlet_complete", {...})` | Run event log |
| 8 | `Skill(agentboard-synthesize-report, ...)` (non-blocking) | Overview report |
| 9 | `AskUserQuestion` + `Skill(agentboard-eng-review \| agentboard-tdd, ...)` | Execution handoff |

---

## Design notes (why this structure)

- **Mechanical by design.** Every scope / architecture / failure-mode decision happened upstream. Lock's only creative work is `atomic_steps` decomposition — and even that is mechanical application of the step-splitter rules.
- **`scope_decision` verbatim from brainstorm.** This is the F4 invariant that makes the single-scope-authority principle hold across the full chain. If lock re-derives, the whole architecture collapses.
- **Legacy fallback exists** because 21+ pre-F4 goals have prose-only upstream artifacts. Lock must still work on them.
- **Step Quality Check is a safety net, not a decision point.** Flagged steps are split suggestions; user can accept or proceed. Lock itself never silently splits.
- **Scope revisit at lock routes back to intent.** Allowing `scope` as a `revise` option at the approval gate would be an F4-equivalent silent-override vector. The answer is always "return to intent".
- **Metadata markers are the downstream contract.** CSO / redteam / approval / ui-preview all read `task.metadata` — getting this right at lock is what makes the rest of the chain work without coordination overhead.
- **`agentboard-tdd` via D1 handoff is sanctioned freeze exemption.** The freeze memory says don't auto-invoke tdd via legacy gauntlet. Invoking tdd as the execution phase after D1 lock is a different path — explicit, logged, and expected until D1f `agentboard-execute` lands.
- **No `--deep` modes by design.** Lock is where re-decisions become dangerous. The symmetry is: intent has `--deep` because it's the creative phase; lock doesn't because it's mechanical.

---

## Freeze notice

Default skill routing still runs the legacy gauntlet's Decide step + Finalize. This skill executes only when explicitly invoked OR when upstream `agentboard-stress` hands off. See `memory/feedback_freeze_gauntlet_flow.md`. At D3 cutover, this skill becomes the canonical lock authority; the legacy gauntlet's Step 5 + Finalize become deprecated.
