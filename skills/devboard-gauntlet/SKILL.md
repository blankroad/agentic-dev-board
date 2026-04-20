---
name: devboard-gauntlet
description: MANDATORY planning gate. Proactively invoke this skill (do NOT write code directly) when the user asks to build, implement, add, create, make, or extend anything involving more than one file, tests, auth, payments, sessions, databases, APIs, architecture decisions, or anything destined for main/production. Runs the 5-step Gauntlet (Frame→Scope→Arch→Challenge→Decide) and locks intent with a SHA256-hashed LockedPlan including atomic_steps and out_of_scope_guard. Skip only for hello-world, one-liners, typo fixes, pure config tweaks, or when the user explicitly says "skip planning".
when_to_use: User asks to build/implement/create/add/make something with multiple files or tests. User says "plan this", "design this", "how should we approach", "think this through", "architect this". MANDATORY before devboard-tdd for non-trivial work. Also invoke when the user says `rethink` or requests replanning.
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

You are the **Planning Gauntlet** — a 5-step intent-locking pipeline adapted from gstack. Run each step sequentially, writing the output to `.devboard/goals/<goal_id>/gauntlet/<step>.md`.

## Step 1 — Frame (problem definition)

Extract from the goal statement:
- **Problem**: 1-2 sentence statement
- **Wedge**: the smallest concrete thing that would prove progress
- **Non-goals**: explicit list of things out of scope
- **Success Definition**: checkable list (each item testable)
- **Key Assumptions**: 2-3 unstated assumptions being relied on
- **Riskiest Assumption**: the one most likely to be wrong

Write → `.devboard/goals/<goal_id>/gauntlet/frame.md`

## Step 2 — Scope (ambition check)

Choose ONE mode:
- **EXPAND**: goal is too small, suggest what to add
- **SELECTIVE**: keep some parts, drop others (specify which)
- **HOLD**: scope is right
- **REDUCE**: goal is too ambitious, suggest what to cut

Output: Rationale (why this mode), Refined Goal Statement, In-scope / Out-of-scope boundaries.

Write → `.devboard/goals/<goal_id>/gauntlet/scope.md`

## Step 3 — Architecture (design lock-in)

- **Architecture Overview**: 2-4 sentence technical approach
- **Data Flow**: input → transformation → output
- **Critical Files**: `path [NEW|MODIFY]: {purpose}` for each file to create/modify — apply Single Responsibility: one file = one feature unit. If a file's purpose statement contains "and", split it.

  ❌ Bad: `src/auth.py [MODIFY]: handles login, session management, and token refresh`
  ✅ Good: `src/auth_login.py [NEW]: login flow`, `src/auth_session.py [NEW]: session management`, `src/auth_token.py [NEW]: token refresh`

- **Edge Cases**: list, each with expected behavior
- **Test Strategy**: what must be tested, what to NOT mock, what's safe to skip
- **Critical Path**: the one thing that MUST work for everything else
- **Out-of-scope Guard**: exact paths/modules the implementation must NOT touch. Optionally annotate each entry with intent — what must NOT happen there:

  ```
  out_of_scope_guard: [
    "src/auth.py — auth only, no session logic",
    "src/models.py — new models go in separate files"
  ]
  ```

Write → `.devboard/goals/<goal_id>/gauntlet/arch.md`

### Complexity Check (run after Critical Files list is complete)

When listing Critical Files, tag each with `[NEW]` or `[MODIFY]`:
- `[NEW]` — file to be newly created
- `[MODIFY]` — existing file to be modified

Then apply the branching below:

Counts: `N = total file count`, `NEW_COUNT = number of [NEW]`, `MODIFY_COUNT = number of [MODIFY]`, `NEW_ABSTRACTIONS = number of new classes/services/modules to create`.

Trigger condition: `N > 8` OR `NEW_ABSTRACTIONS ≥ 2`.

**Case 1: No trigger** → Output one line and proceed to Challenge immediately:
`✅ Complexity OK: {N} files ({NEW_COUNT} new, {MODIFY_COUNT} modified, {NEW_ABSTRACTIONS} new abstractions).`

**Case 2: Trigger fired AND MODIFY_COUNT ≥ NEW_COUNT** → possible scope creep:
- AskUserQuestion: "이 계획은 기존 파일 {MODIFY_COUNT}개를 포함해 총 {N}개를 건드립니다 (새 abstraction {NEW_ABSTRACTIONS}개). 같은 목표를 더 적은 변경으로 달성할 수 있을까요? scope를 줄이거나 그대로 진행할 수 있습니다."
- User picks scope reduction → rewrite Arch and re-run Complexity Check
- User picks proceed-as-is → output `⚠️ Scope creep risk: {N} files modified. Proceeding as-is.` and proceed to Challenge

**Case 3: Trigger fired AND NEW_COUNT > MODIFY_COUNT** → inherent complexity of a new system:
- Output `⚠️ New system: {NEW_COUNT} new files, {NEW_ABSTRACTIONS} new abstractions. Engineering review recommended.`
- Proceed to Challenge immediately (no scope reduction prompt)

### arch.md footer (flag persistence)

Append the machine-readable section below at the end of arch.md. The Finalize step re-reads this file to branch.

```
---
## Meta (machine-readable, do not edit)
COMPLEXITY_CASE: 1 | 2 | 3
ENG_REVIEW_NEEDED: true | false    # true only when Case 3
NEW_COUNT: {NEW_COUNT}
MODIFY_COUNT: {MODIFY_COUNT}
NEW_ABSTRACTIONS: {NEW_ABSTRACTIONS}
```

## Step 4 — Challenge (red-team the plan)

Find at least 4 failure modes of the PLAN (not the code yet):
- Scope drift risks
- Architectural flaws
- Missing edge cases
- Integration gaps
- Test coverage gaps

For each: severity (CRITICAL / HIGH / MEDIUM), mitigation, and "warrants replan?" yes/no.

Write → `.devboard/goals/<goal_id>/gauntlet/challenge.md`

## Step 5 — Decide (synthesize LockedPlan)

Synthesize the prior 4 into a JSON matching this schema:

```json
{
  "problem": "...",
  "non_goals": ["..."],
  "scope_decision": "EXPAND|SELECTIVE|HOLD|REDUCE",
  "architecture": "...",
  "known_failure_modes": ["CRITICAL: ...", "HIGH: ..."],
  "goal_checklist": ["...checkable items..."],
  "out_of_scope_guard": ["...paths..."],
  "atomic_steps": [
    {
      "id": "s_001",
      "behavior": "ONE testable behavior (2-5 min of work)",
      "test_file": "relative path",
      "test_name": "function name",
      "impl_file": "relative path or ''",
      "expected_fail_reason": "e.g. NameError: add not defined"
    }
  ],
  "token_ceiling": 100000,
  "max_iterations": 5,
  "integration_test_command": "",
  "borderline_decisions": [
    {"question": "...", "option_a": "...", "option_b": "...", "recommendation": "A"}
  ]
}
```

**`integration_test_command` (optional)**: shell command that approval runs before push as a smoke gate. Non-zero exit refuses push. Empty string skips the gate. Example: `"pytest tests/e2e -x"` or `"make smoke"`. Not included in `compute_hash` — changing the command after lock does not re-hash the plan.

## atomic_steps guidance (TDD mode)

Each atomic_step = ONE red-green-refactor cycle. Decompose the goal_checklist into the smallest verifiable behaviors:
- ~2-5 min of work per step
- One assertion, one behavior — NOT "implement add/sub/mul/div" but four separate steps
- Order so earlier steps are prerequisites for later
- Error-path behaviors are distinct steps ("div(a, 0) raises ZeroDivisionError" is its own step)

**Step quality — Bad: vs Good:**

❌ Bad: `"implement auth flow with login, logout, and session validation"`
- Covers 3 behaviors. RED test would need 3 assertions. GREEN impl grows too large.

✅ Good: (same goal, split correctly into 3 steps)
- `s_001`: `"POST /auth/login with valid creds returns 200 + token"`
- `s_002`: `"POST /auth/logout invalidates the session token"`
- `s_003`: `"GET /api/protected with expired token returns 401"`

**Step splitter trigger**: if the behavior contains "and", "with", or references multiple impl files → split into separate steps, one assertion each. This is a heuristic, not a hard rule — use judgment for behaviors that are genuinely atomic despite containing those words.

## Step Quality Review

After generating all `atomic_steps` in the Decide JSON, self-review each step before presenting to the user:

```
## Step Quality Check

Checking each step: one behavior, one assertion, ≤5 min work.

✅ s_001: OK
⚠️  s_003: behavior contains "and" — may cover 2 behaviors
    Suggestion: split into s_003a / s_003b
✅ s_004: OK
```

- If all steps pass: output one line — "Step quality: all OK — proceeding to lock." No user interaction.
- If any warning: list flagged steps with split suggestion. Ask: "Adjust these steps or proceed to lock as-is?"

## Finalize

After Decide produces the JSON:

1. Resolve any `borderline_decisions` with the user (one question at a time, offer A/B + your recommendation)
2. Present the plan to the user for review. Ask: "Plan ready. Approve to lock? (yes / no + which step to revise: problem|scope|arch|challenge)"
3. If approved: call `devboard_approve_plan(project_root, goal_id, approved=True)`
4. If revision needed: call `devboard_approve_plan(project_root, goal_id, approved=False, revision_target=<step>)`, then re-run from that step
5. Once approved, call `devboard_lock_plan(goal_id, decide_json, project_root)` which:
   - Verifies `plan_review.json` status=approved (returns error if missing or revision_pending)
   - Computes SHA256 hash of the locked fields
   - Writes `.devboard/goals/<goal_id>/plan.md` (human-readable) and `plan.json` (machine-readable)
   - Returns the locked_hash

The plan is now **immutable**. Implementation must follow it. Any drift triggers a `rethink`.

### Task metadata markers (run after start_task)

Right after receiving `task_id` from `devboard_start_task`, set the markers below automatically — so CSO/redteam can decide entry deterministically:

1. **production_destined**: default `true`. Only `false` if the user explicitly said "throwaway" or "prototype".
2. **security_sensitive_plan**: concatenate the architecture/atomic_steps text from arch.md + decide.json into a single string, then call `devboard_check_security_sensitive(diff=<plan_text>)`. Use the returned `sensitive` value as-is.
3. **ui_surface**: concatenate arch.md + decide.json into a single string, then scan case-insensitively for any of these keywords: `tui`, `textual`, `widget`, `pilot`, `browser`, `ui`, `frontend`. If any keyword is present → `True`, else `False`. This flag lets `devboard-approval` decide whether to capture a real-TTY screenshot via `devboard_tui_render_smoke` and write the `## Screenshots / Diagrams` section of plan.md.

Save all three values like this:

```
devboard_update_task_status(
  project_root, task_id, status="planning",
  metadata={
      "production_destined": <bool>,
      "security_sensitive_plan": <bool>,
      "ui_surface": <bool>,
  }
)
```

The CSO/redteam skills read the first two markers to decide whether to auto-run. Approval reads `ui_surface` to decide whether to run the real-TTY smoke capture.

## Required MCP calls

You MUST call these in order. Missing a call leaves `.devboard/` incomplete and breaks retro/replay.

| When | Tool | Purpose |
|---|---|---|
| After user reviews Decide output | `devboard_approve_plan(project_root, goal_id, approved, revision_target?)` | Record plan review decision |
| After approval confirmed | `devboard_lock_plan(project_root, goal_id, decide_json)` | Computes SHA256, writes plan.md + plan.json |
| Right after lock | `devboard_start_task(project_root, goal_id)` | Creates Task + starts run. Returns `{task_id, run_id}` — SAVE BOTH. |
| After lock + start_task | `devboard_checkpoint(project_root, run_id, "gauntlet_complete", {...})` | Record Gauntlet completion with locked_hash + atomic_steps count |

The `task_id` and `run_id` you receive from `devboard_start_task` MUST be threaded through to `devboard-tdd` and all subsequent MCP calls in this session.

## Handoff

After locking + start_task + checkpoint:

1. Read the Meta section of arch.md and check the `ENG_REVIEW_NEEDED` value
2. Branch:
   - **ENG_REVIEW_NEEDED = false** → invoke `devboard-tdd` via Skill tool immediately
   - **ENG_REVIEW_NEEDED = true** → AskUserQuestion:
     "이 계획은 {NEW_COUNT}개의 새 파일 + {NEW_ABSTRACTIONS}개 새 abstraction을 포함합니다. TDD 시작 전 engineering review를 실행할까요? (권장) [Y/n]"
     - Y (default) → invoke `devboard-eng-review` via Skill tool. **After this, gauntlet does NOT call tdd directly** — eng-review invokes tdd itself when complete.
     - n → invoke `devboard-tdd` via Skill tool immediately.

Thread `{task_id, run_id}` through all subsequent MCP calls.

---

## UI Preview integration (when ui_surface=True)

Right after `arch.md` is written and BEFORE proceeding to Challenge, check `task.metadata.ui_surface`:

- **ui_surface=False** → skip this section, go to Challenge as usual.
- **ui_surface=True** → invoke `devboard-ui-preview` via the Skill tool with `layer=0` in the argument payload. That skill produces a Layer 0 ASCII mockup, asks the user to confirm, and records the confirmed mockup SHA back into arch.md so the gauntlet hash covers the visual intent. Only after user confirmation resume the Gauntlet at Step 4 (Challenge).

Rationale: arch.md describes layout in prose, which is lossy. For `ui_surface=True` tasks, the Layer 0 mockup is the cheapest way to let the user catch "that's not what I pictured" before any code is written. See `skills/devboard-ui-preview/SKILL.md` for the full Layer 0 flow.
