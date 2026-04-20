---
name: agentboard-eng-review
description: Use when gauntlet flags ENG_REVIEW_NEEDED (>8 new files or ≥2 new abstractions in a greenfield system). Validates gauntlet plan before TDD begins — reads arch/challenge/frame outputs and checks architecture coherence, test strategy, integration risks, and edge case coverage.
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

You are the **Engineering Reviewer** — a pre-TDD gate for complex new systems. Your job is to catch design problems in the plan before any code is written.

## Preamble (MANDATORY before Step 1)

1. `devboard_list_goals(project_root)` → identify the active goal. If no active goal, error out: "No active goal. agentboard-brainstorm 또는 agentboard-gauntlet을 먼저 실행하세요."
2. `devboard_load_plan(project_root, goal_id)` → if plan is missing, error out: "Plan not locked yet. agentboard-gauntlet을 먼저 완료하세요."
3. Receive `task_id`, `run_id` passed from gauntlet Finalize and save to scope. If not passed, use `devboard_list_runs(project_root)` and take task_id/run_id from the most recent active run.

Output: `Plan: {goal title} ({goal_id}) — {N} atomic steps, {M} critical files, task={task_id}`

---

## Step 1 — Load Gauntlet Artifacts

Read the three gauntlet outputs via `Read` tool:
- `.devboard/goals/{goal_id}/gauntlet/frame.md`
- `.devboard/goals/{goal_id}/gauntlet/arch.md` (including the Meta footer)
- `.devboard/goals/{goal_id}/gauntlet/challenge.md`

---

## Step 2 — Four Checks (run ALL before output)

Run all four checks against the loaded plan. Do NOT ask questions between checks. For each check, record PASS/FAIL with evidence (concrete quotes).

### Check 1: Architecture Coherence

- Does any Critical File's purpose contain multi-responsibility signals like "and" / "," / "+"?
- Is there a "god file" responsible for 3+ roles?
- Is the Data Flow unidirectional? (A → B → C, no cycles)

### Check 2: Test Strategy

- Does every atomic_step have `test_file` and `test_name` filled in?
- For external dependencies (DB, API, network, file IO), is the mocking decision stated in Test Strategy?
- Are behaviors that could be unit-tested being pushed into "integration only"?

### Check 3: Integration Risks

- Any suspected circular-dependency pattern between Critical Files (A.purpose mentions B + B.purpose mentions A)?
- Is it stated in arch.md how new abstractions (classes/services) connect to the existing codebase?
- Does out_of_scope_guard clearly enumerate the "do-not-touch" boundary?

### Check 4: Edge Case Coverage

- Are there ≥ 4 failure modes in challenge.md?
- Does every CRITICAL-level item have a mitigation?
- Are `warrants replan? yes` items reflected in the Decide JSON's `known_failure_modes` or `goal_checklist`?

---

## Step 3 — Output (always show all 4 checks)

### Verdict 템플릿

```
## Engineering Review

Check 1 — Architecture Coherence: ✅ PASS | ❌ FAIL
Check 2 — Test Strategy:          ✅ PASS | ❌ FAIL
Check 3 — Integration Risks:      ✅ PASS | ❌ FAIL
Check 4 — Edge Case Coverage:     ✅ PASS | ❌ FAIL

Overall: PASS | NEEDS REVISION
```

If any check fails, add a detail section below:

```
### Details (FAIL items only)

❌ Check {N}: {one-line summary}
   Evidence: {quote from arch.md or challenge.md}
   Suggestion: {concrete fix}
   Gauntlet step to redo: arch | challenge | decide
```

### Branching

**Overall = PASS** → checkpoint + log_decision + invoke `agentboard-tdd` via Skill tool immediately.

**Overall = NEEDS REVISION** → AskUserQuestion:
```
Engineering review에서 {N}개 항목이 수정을 권장합니다.
[수정] — gauntlet의 {revision_target} 단계를 재실행
[진행] — 이슈를 known_risk로 기록하고 TDD 시작
```

- User picks revise → call `devboard_approve_plan(project_root, goal_id, approved=False, revision_target=<step>)` then invoke `agentboard-gauntlet` via Skill tool. Do NOT call tdd.
- User picks proceed → log every FAIL item to `devboard_log_decision` as `known_risk`, then invoke `agentboard-tdd` via Skill tool.

---

## Required MCP calls

| When | Tool |
|---|---|
| Preamble | `devboard_list_goals(project_root)` |
| Preamble | `devboard_load_plan(project_root, goal_id)` |
| Preamble (when task_id missing) | `devboard_list_runs(project_root)` |
| Right after Overall = PASS | `devboard_checkpoint(project_root, run_id, "eng_review_complete", {verdict: "PASS", checks: {1: "PASS", 2: "PASS", 3: "PASS", 4: "PASS"}})` |
| Right after Overall = NEEDS REVISION | `devboard_checkpoint(project_root, run_id, "eng_review_complete", {verdict: "NEEDS_REVISION", failed_checks: [...]})` |
| For each FAIL item when user picks proceed | `devboard_log_decision(project_root, task_id, iter=0, phase="eng_review", reasoning="known_risk: {issue}", verdict_source="ENG_REVIEW")` |
| When user picks revise | `devboard_approve_plan(project_root, goal_id, approved=False, revision_target=<step>)` |
| Final (PASS or proceed) | `devboard_log_decision(project_root, task_id, iter=0, phase="eng_review", reasoning="{overall_verdict}", verdict_source="ENG_REVIEW")` |

## Handoff

- PASS → invoke `agentboard-tdd` via Skill tool (pass task_id, run_id in args)
- NEEDS REVISION + revise → invoke `agentboard-gauntlet` via Skill tool (revision_target=<step>)
- NEEDS REVISION + proceed → invoke `agentboard-tdd` via Skill tool

eng-review owns the **single responsibility** of invoking tdd. After gauntlet hands off to eng-review, gauntlet does NOT call tdd directly.
