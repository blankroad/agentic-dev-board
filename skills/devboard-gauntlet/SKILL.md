---
name: devboard-gauntlet
description: MANDATORY planning gate. Proactively invoke this skill (do NOT write code directly) when the user asks to build, implement, add, create, make, or extend anything involving more than one file, tests, auth, payments, sessions, databases, APIs, architecture decisions, or anything destined for main/production. Runs the 5-step Gauntlet (Frame→Scope→Arch→Challenge→Decide) and locks intent with a SHA256-hashed LockedPlan including atomic_steps and out_of_scope_guard. Skip only for hello-world, one-liners, typo fixes, pure config tweaks, or when the user explicitly says "skip planning".
when_to_use: User asks to build/implement/create/add/make something with multiple files or tests. User says "plan this", "design this", "how should we approach", "think this through", "architect this". MANDATORY before devboard-tdd for non-trivial work. Also invoke when the user says `rethink` or requests replanning.
---

> **언어**: 사용자와의 대화·진행 보고·질문·결과 요약은 모두 **한국어**로. 코드·파일 경로·변수명·커밋 메시지·Gauntlet 산출물 문서는 영어 유지.

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
- **Critical Files**: `path: {purpose}` for each file to create/modify — apply Single Responsibility: one file = one feature unit. If a file's purpose statement contains "and", split it.

  ❌ Bad: `src/auth.py: handles login, session management, and token refresh`
  ✅ Good: `src/auth_login.py: login flow`, `src/auth_session.py: session management`, `src/auth_token.py: token refresh`

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

Critical Files를 나열할 때 각 파일에 `[NEW]` / `[MODIFY]` 태그를 명시:
- `[NEW]` — 새로 생성할 파일
- `[MODIFY]` — 기존 파일 수정

그런 다음 아래 분기를 적용:

**Case 1: 파일 수 ≤ 8** → 한 줄 출력 후 즉시 Challenge로 이동:
`✅ Complexity OK: {N} files ({NEW_COUNT} new, {MODIFY_COUNT} modified).`

**Case 2: 파일 수 > 8 AND [MODIFY] 파일이 절반 이상** → scope creep 가능성:
- AskUserQuestion: "이 계획은 기존 파일 {MODIFY_COUNT}개를 포함해 총 {N}개를 건드립니다. 같은 목표를 더 적은 변경으로 달성할 수 있을까요? scope를 줄이거나 그대로 진행할 수 있습니다."
- scope 축소 선택 → Arch 재작성 후 Complexity Check 재실행
- 그대로 진행 → `⚠️ Scope creep risk: {N} files modified. Proceeding as-is.` 출력 후 Challenge로 이동

**Case 3: 파일 수 > 8 AND [NEW] 파일이 절반 초과** → 새 시스템 고유 복잡도:
- `⚠️ New system: {NEW_COUNT} new files. Engineering review recommended.` 출력
- `ENG_REVIEW_NEEDED = true` 플래그 설정 (Finalize에서 참조)
- 즉시 Challenge로 이동 (scope 축소 제안 없음)

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
  "borderline_decisions": [
    {"question": "...", "option_a": "...", "option_b": "...", "recommendation": "A"}
  ]
}
```

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

- **ENG_REVIEW_NEEDED = false** → 즉시 `devboard-tdd` 호출
- **ENG_REVIEW_NEEDED = true** → AskUserQuestion:
  "이 계획은 {NEW_COUNT}개의 새 파일을 포함합니다. TDD 시작 전 engineering review를 실행할까요? (권장) [y/N]"
  - y → Skill tool로 `devboard-eng-review` 호출. eng-review 완료 후 `devboard-tdd` 호출.
  - N → 즉시 `devboard-tdd` 호출.

`{task_id, run_id}`는 모든 후속 MCP 호출에 전달.
