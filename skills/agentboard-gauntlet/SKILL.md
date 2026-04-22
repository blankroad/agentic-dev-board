---
name: agentboard-gauntlet
description: MANDATORY planning gate. Proactively invoke this skill (do NOT write code directly) when the user asks to build, implement, add, create, make, or extend anything involving more than one file, tests, auth, payments, sessions, databases, APIs, architecture decisions, or anything destined for main/production. Runs the 4-step Gauntlet (Frame→Arch→Challenge→Decide) and locks intent with a SHA256-hashed LockedPlan. Scope decisions come from `agentboard-brainstorm` Phase 4 via brainstorm.md YAML frontmatter — the gauntlet no longer re-decides scope. including atomic_steps and out_of_scope_guard. Skip only for hello-world, one-liners, typo fixes, pure config tweaks, or when the user explicitly says "skip planning".
when_to_use: User asks to build/implement/create/add/make something with multiple files or tests. User says "plan this", "design this", "how should we approach", "think this through", "architect this". MANDATORY before agentboard-tdd for non-trivial work. Also invoke when the user says `rethink` or requests replanning.
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

## Preamble — Project Guard (MANDATORY first check)

Before any other action, verify agentboard is initialized in this project. Run this Bash command:

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

- Output `MISSING` → print this message to the user and **exit the skill immediately** (do NOT call any MCP tools, do NOT proceed with any steps below):
  > agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill.
- Output `OK` → proceed with the skill below.

You are the **Planning Gauntlet** — a 4-step intent-locking pipeline adapted from gstack. Run each step sequentially, writing the output to `.devboard/goals/<goal_id>/gauntlet/<step>.md`.

**Scope authority (F4):** Scope decisions (EXPAND / SELECTIVE / HOLD / REDUCE) are owned by `agentboard-brainstorm`, not the gauntlet. Read `brainstorm.md` YAML frontmatter and use its `scope_mode` verbatim. The gauntlet no longer has a Step 2 Scope — running one here would re-litigate a decision the user already confirmed.

## Step 1 — Frame (problem definition)

**First, read `brainstorm.md` frontmatter** (if present at `.devboard/goals/<goal_id>/brainstorm.md`) and use these fields as inputs:

- `scope_mode` → carry into Step 4 Decide as `scope_decision` (do NOT re-derive)
- `refined_goal` → use as the 1-sentence problem statement root
- `wedge` → use as the Frame `Wedge` field directly
- `req_list` items with `status: deferred` → seed into `Non-goals`
- `rationale` → preserve as context for Step 3 Arch

If `brainstorm.md` is missing or lacks frontmatter (legacy goal), default `scope_mode=HOLD` at Step 4 and log a `no_brainstorm_frontmatter` marker to decisions.jsonl at that time.

Extract from the goal statement + brainstorm frontmatter:

- **Problem**: 1-2 sentence statement (root from `refined_goal` if present)
- **Wedge**: the smallest concrete thing that would prove progress (from brainstorm `wedge` if present)
- **Non-goals**: explicit list of things out of scope (seeded from brainstorm `req_list` deferred entries)
- **Success Definition**: checkable list (each item testable)
- **Key Assumptions**: 2-3 unstated assumptions being relied on
- **Riskiest Assumption**: the one most likely to be wrong

Write → `.devboard/goals/<goal_id>/gauntlet/frame.md`

## Step 2 — Architecture (design lock-in)

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

**Scope authority (F4):** This check sets `ENG_REVIEW_NEEDED` only — it does NOT re-decide scope. Scope is owned by `agentboard-brainstorm` Phase 4 and recorded in `brainstorm.md` frontmatter. Prior versions had a "Case 2: scope creep" AskUserQuestion that asked the user to cut scope mid-gauntlet; that was removed in F4 because it silently overrode the user's Phase 4 confirmation.

When listing Critical Files, tag each with `[NEW]` or `[MODIFY]`:

- `[NEW]` — file to be newly created
- `[MODIFY]` — existing file to be modified

Then apply the branching below.

Counts: `N = total file count`, `NEW_COUNT = number of [NEW]`, `MODIFY_COUNT = number of [MODIFY]`, `NEW_ABSTRACTIONS = number of new classes/services/modules to create`.

Trigger condition: `N > 8` OR `NEW_ABSTRACTIONS ≥ 2`.

**Case 1: No trigger** → output one line and proceed to Challenge:
`✅ Complexity OK: {N} files ({NEW_COUNT} new, {MODIFY_COUNT} modified, {NEW_ABSTRACTIONS} new abstractions).`

**Case 2: Trigger fired** → engineering review recommended (ENG_REVIEW_NEEDED flag only — no scope prompt):
- Output `⚠️ {NEW_COUNT} new files, {MODIFY_COUNT} modified, {NEW_ABSTRACTIONS} new abstractions. Engineering review recommended.`
- Set `ENG_REVIEW_NEEDED: true` in the arch.md Meta footer.
- Proceed to Challenge immediately. Do NOT prompt the user to reduce scope — if scope feels wrong, the answer is to return to `agentboard-brainstorm`, not to cut inside the gauntlet.

### arch.md footer (flag persistence)

Append the machine-readable section below at the end of arch.md. The Finalize step re-reads this file to branch on ENG_REVIEW_NEEDED.

```
---
## Meta (machine-readable, do not edit)
COMPLEXITY_CASE: 1 | 2                  # 1 = no trigger, 2 = ENG_REVIEW_NEEDED
ENG_REVIEW_NEEDED: true | false         # true only when Case 2
NEW_COUNT: {NEW_COUNT}
MODIFY_COUNT: {MODIFY_COUNT}
NEW_ABSTRACTIONS: {NEW_ABSTRACTIONS}
```

## Step 3 — Challenge (red-team the plan)

Find at least 4 failure modes of the PLAN (not the code yet):
- Scope drift risks
- Architectural flaws
- Missing edge cases
- Integration gaps
- Test coverage gaps

For each: severity (CRITICAL / HIGH / MEDIUM), mitigation, and "warrants replan?" yes/no.

Write → `.devboard/goals/<goal_id>/gauntlet/challenge.md`

## Step 4 — Decide (synthesize LockedPlan)

Synthesize the prior 3 steps (Frame + Arch + Challenge) into a JSON matching this schema.

**`scope_decision` injection (F4):** Do NOT derive `scope_decision` here — read it from `brainstorm.md` YAML frontmatter at the start of the session:

- If `brainstorm.md` has `scope_mode: <EXPAND|SELECTIVE|HOLD|REDUCE>` in its frontmatter → use that value verbatim as `scope_decision`.
- If `brainstorm.md` is missing OR has no `scope_mode` field → default to `"HOLD"` AND emit a `agentboard_log_decision(phase="plan", reasoning="no brainstorm frontmatter; defaulted scope_decision=HOLD", verdict_source="default_hold")` marker for retro visibility.
- Never invent a `scope_decision` different from the brainstorm frontmatter. If you believe the user's Phase 4 choice is wrong, the correct path is to return to `agentboard-brainstorm` and redo Phase 4 — NOT to override here.

```json
{
  "problem": "...",
  "non_goals": ["..."],
  "scope_decision": "<verbatim from brainstorm.md frontmatter scope_mode, or HOLD default>",
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
2. Present the plan to the user for review. Ask: "Plan ready. Approve to lock? (yes / no + which step to revise: problem|arch|challenge)". Note: `scope` is not revisable here — if scope is wrong, return to `agentboard-brainstorm` Phase 4 instead.
3. If approved: call `agentboard_approve_plan(project_root, goal_id, approved=True)`
4. If revision needed: call `agentboard_approve_plan(project_root, goal_id, approved=False, revision_target=<step>)`, then re-run from that step
5. Once approved, call `agentboard_lock_plan(goal_id, decide_json, project_root)` which:
   - Verifies `plan_review.json` status=approved (returns error if missing or revision_pending)
   - Computes SHA256 hash of the locked fields
   - Writes `.devboard/goals/<goal_id>/plan.md` (human-readable) and `plan.json` (machine-readable)
   - Returns the locked_hash

The plan is now **immutable**. Implementation must follow it. Any drift triggers a `rethink`.

### Task metadata markers (run after start_task)

Right after receiving `task_id` from `agentboard_start_task`, set the markers below automatically — so CSO/redteam can decide entry deterministically:

1. **production_destined**: default `true`. Only `false` if the user explicitly said "throwaway" or "prototype".
2. **security_sensitive_plan**: concatenate the architecture/atomic_steps text from arch.md + decide.json into a single string, then call `agentboard_check_security_sensitive(diff=<plan_text>)`. Use the returned `sensitive` value as-is.
3. **ui_surface**: concatenate arch.md + decide.json into a single string, then scan case-insensitively for any of these keywords: `tui`, `textual`, `widget`, `pilot`, `browser`, `ui`, `frontend`. If any keyword is present → `True`, else `False`. This flag lets `agentboard-approval` decide whether to capture a real-TTY screenshot via `agentboard_tui_render_smoke` and write the `## Screenshots / Diagrams` section of plan.md.

Save all three values like this:

```
agentboard_update_task_status(
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
| After user reviews Decide output | `agentboard_approve_plan(project_root, goal_id, approved, revision_target?)` | Record plan review decision |
| After approval confirmed | `agentboard_lock_plan(project_root, goal_id, decide_json)` | Computes SHA256, writes plan.md + plan.json |
| Right after lock | `agentboard_start_task(project_root, goal_id)` | Creates Task + starts run. Returns `{task_id, run_id}` — SAVE BOTH. |
| After lock + start_task | `agentboard_checkpoint(project_root, run_id, "gauntlet_complete", {...})` | Record Gauntlet completion with locked_hash + atomic_steps count |

The `task_id` and `run_id` you receive from `agentboard_start_task` MUST be threaded through to `agentboard-tdd` and all subsequent MCP calls in this session.

## Handoff

After locking + start_task + checkpoint:

0. **Generate provisional Overview report (non-blocking).** Invoke `agentboard-synthesize-report` via the `Skill` tool with `goal_id=<goal_id>`. This writes `.devboard/goals/<goal_id>/report.md` so the TUI Overview tab renders release-notes-style content even before any TDD cycle runs. The skill catches its own failures and logs `NARRATIVE_SKIPPED` by contract — wrap the invocation in try/except conceptually, never gate the rest of the handoff on its success. Rationale: the Overview tab used to be empty until approval ran synthesize-report, so 95% of in-flight goals showed only the legacy plan_digest metadata dump.
1. Read the Meta section of arch.md and check the `ENG_REVIEW_NEEDED` value
2. Branch:
   - **ENG_REVIEW_NEEDED = false** → invoke `agentboard-tdd` via Skill tool immediately
   - **ENG_REVIEW_NEEDED = true** → AskUserQuestion:
     "이 계획은 {NEW_COUNT}개의 새 파일 + {NEW_ABSTRACTIONS}개 새 abstraction을 포함합니다. TDD 시작 전 engineering review를 실행할까요? (권장) [Y/n]"
     - Y (default) → invoke `agentboard-eng-review` via Skill tool. **After this, gauntlet does NOT call tdd directly** — eng-review invokes tdd itself when complete.
     - n → invoke `agentboard-tdd` via Skill tool immediately.

Thread `{task_id, run_id}` through all subsequent MCP calls.

---

## UI Preview integration (when ui_surface=True)

Right after `arch.md` is written and BEFORE proceeding to Challenge, check `task.metadata.ui_surface`:

- **ui_surface=False** → skip this section, go to Challenge as usual.
- **ui_surface=True** → invoke `agentboard-ui-preview` via the Skill tool with `layer=0` in the argument payload. That skill produces a Layer 0 ASCII mockup, asks the user to confirm, and records the confirmed mockup SHA back into arch.md so the gauntlet hash covers the visual intent. **After Layer 0 is confirmed, and BEFORE proceeding to Challenge, invoke `agentboard-design-review` via the Skill tool.** design-review scores the arch + mockup against a 7-pass UI/UX rubric (Information Architecture, Interaction State Coverage incl. modal stacking / focus trap / z-order, User Journey, AI Slop Risk, Design System Alignment, Responsive+Keyboard, Unresolved Decisions):

  - verdict `APPROVED` or `WARN` → resume the Gauntlet at Step 3 (Challenge). WARN means fix proposals were upserted into arch.md's `## Design Review` section for Challenge to read.
  - verdict `BLOCKER` → return to Step 2 (Architecture) for rewrite. design-review enforces a 1-retry cap + user override escape hatch (`BLOCKER_OVERRIDDEN` sentinel) so the loop cannot run forever.
  - verdict `NOT_APPLICABLE` → the deliverable is not a mountable UI (e.g. a meta-goal whose impl_file is a markdown skill doc). Skip straight to Step 3 (Challenge).

Rationale: arch.md describes layout in prose, which is lossy. For `ui_surface=True` tasks, the Layer 0 mockup is the cheapest way to let the user catch "that's not what I pictured" before any code is written, and the design-review gate catches interaction-level UX bugs (e.g. "화면 분할이 모달 뒤에서 일어남") before they reach TDD. See `skills/agentboard-ui-preview/SKILL.md` for the Layer 0 flow and `skills/agentboard-design-review/SKILL.md` for the 7-pass rubric.
