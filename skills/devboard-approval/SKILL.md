---
name: devboard-approval
description: Final approval gate before git push + PR. Proactively invoke this skill (do NOT git push directly) when the user says "ship it", "ship", "open a PR", "merge this", "push it", "deploy", "make a PR", "land this", OR after loop convergence (reviewer PASS + CSO SECURE + red-team SURVIVED + all checklist items verified). Summarizes diff stats, goal checklist verification, iteration stats, and key decisions. Prompts user for squash policy (squash/semantic/preserve/interactive). Builds PR body from LockedPlan + decisions automatically. Creates PR via `gh pr create`. NEVER force-pushes. REFUSES to push if any checklist item unverified or CSO returned VULNERABLE.
when_to_use: User signals readiness to push/merge/ship. Automatic after devboard-redteam SURVIVED (or after devboard-tdd full green + checklist verified if red-team was skipped). Voice triggers - "ship it", "land it", "open a PR", "push this up".
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

You are the **Approval Gate**. Loop converged → present to user → push on approval.

## Step 0 — Pre-approval Guard (MANDATORY before Step 1)

On entry, call `devboard_load_decisions(project_root, task_id)` and verify these conditions:

1. **TDD complete check** — does a `phase="reflect"` or `phase="review_complete"` entry exist?
   - If missing, **refuse**: "TDD가 완료되지 않았습니다. devboard-tdd를 먼저 실행하세요." → exit skill
2. **CSO necessity check** — if the diff or LockedPlan contains security-sensitive keywords (auth, password, token, crypto, SQL, subprocess, eval, exec), verify a `phase="cso"` entry exists.
   - If missing, **refuse**: "보안 민감 변경이 감지됐으나 CSO 검토가 없습니다. devboard-cso를 먼저 실행하세요." → exit skill
3. **CSO verdict check** — if a `phase="cso"` entry exists, verify its verdict is not `VULNERABLE`.
   - If `VULNERABLE`, **refuse**: "CSO returned VULNERABLE. 이슈 해결 후 재시도." → exit skill
4. **Dep audit check** — call `devboard_check_dependencies(project_root)`.
   - If `skipped_reason` is set → pass (audit unavailable)
   - If `severity_counts.CRITICAL ≥ 1` or `severity_counts.HIGH ≥ 1` → **refuse**: "Dep audit VULNERABLE: CRITICAL={c}, HIGH={h}. devboard-dep-audit를 실행해서 세부 확인 후 업그레이드 필요." → exit skill
   - Otherwise → pass

If all four conditions pass, proceed to Step 1.

## Step 1 — Summarize for user

Present, in this order:

### Diff stats
Call MCP tool `devboard_get_diff_stats(project_root)` → show file/lines summary.

### Checklist verification
Load LockedPlan via `devboard_load_plan(goal_id)`. For each checklist item, mark ✓ (verified by `devboard_verify`) or ✗ (must block PR).

### Iteration stats
Call `devboard_load_decisions(task_id)`:
- Iterations completed
- Retries count
- RETRY reasons (top 3)
- RED-GREEN cycles completed
- CSO verdict (if ran)
- Red-team verdict (if ran)

### Key decisions
Last 3 `reflect` phase entries from decisions — what was learned.

## Step 2 — Squash policy prompt

Offer the user 4 options:

| # | Policy | Effect |
|---|---|---|
| 1 | **squash** (default) | All iter commits → 1 clean commit on push. PR body has decisions summary. |
| 2 | **semantic** | Keep iter commits as-is (often already one-per-task). |
| 3 | **preserve** | All iter commits kept. Full audit trail in git. |
| 4 | **interactive** | User runs `git rebase -i` manually before push. |

Default = squash. Ask: "Policy? [1/2/3/4]"

## Step 3 — Final confirmation

Show the constructed PR body (call `devboard_build_pr_body(plan, decisions, iterations)`). Ask: "Approve and push? [y/N]"

If N: task stays in `awaiting_approval` state. User can edit manually.

## Step 3.5 — Smoke gate (if integration_test_command present)

At entry, check `integration_test_command` via `devboard_load_plan`:

- If empty string, skip this step (output one line: "No smoke test defined — skipping gate.")
- If a command is present:
  1. Call `devboard_check_command_safety(command)` first for safety
  2. Run via Bash tool and check the exit code
  3. exit=0 → smoke PASS, proceed to Step 4
  4. exit≠0 → smoke FAIL, refuse push, task stays in `awaiting_approval`, output a stderr summary

## Step 4 — Push

On y:

1. Call `devboard_apply_squash_policy(project_root, branch, base_branch, policy, squash_message)` to reshape commits per policy
2. Call `devboard_push_pr(project_root, branch, pr_title, pr_body, base_branch, draft)` which:
   - `git push -u origin <branch>`
   - `gh pr create --title ... --body "<body>" --base <base_branch>`
3. Update task status to `pushed` via `devboard_update_task_status(task_id, 'pushed')`
4. Report the PR URL to the user

## Failure modes

- **Push fails**: network / auth issues. Report error. Task remains in `awaiting_approval`.
- **gh not installed**: fall back — push only, tell user to open PR manually with the pre-built body.
- **Checklist has ✗ items**: refuse to push. Hand back to `devboard-tdd`.
- **Uncommitted changes**: refuse — must be clean working tree first.

## Required MCP calls — ALL mandatory, in order

**The `converged` checkpoint is a HARD REQUIREMENT** whether push succeeded, was skipped (no remote), or was rejected by user. Without it, diagnose shows skill_activation_score < 100%.

| When | Tool | Notes |
|---|---|---|
| On entry | `devboard_load_plan(project_root, goal_id)` + `devboard_load_decisions(project_root, task_id)` | Build summary |
| Before asking user | `devboard_get_diff_stats(project_root)` | |
| Before asking user | `devboard_verify(project_root, checklist)` | Re-verify fresh |
| On user approval | `devboard_apply_squash_policy(project_root, branch, base_branch, policy, message)` | |
| Build PR body | `devboard_build_pr_body(project_root, goal_id, task_id, iterations_completed, diff_stats)` | |
| Push (if remote) | `devboard_push_pr(project_root, branch, pr_title, pr_body, base_branch)` | |
| **Always** after push/commit | `devboard_checkpoint(project_root, run_id, "converged", {pr_url_or_reason, policy, iterations})` | **MANDATORY — even if local-only ship** |
| **Always** after converged | `devboard_update_task_status(project_root, task_id, "pushed")` | |
| **Always** after converged | `devboard_log_decision(project_root, task_id, iter=N, phase="approval", reasoning=<pr_url_or_reason>, verdict_source="PUSHED")` | |

## Discipline

- NEVER `git push --force`
- NEVER skip the checklist verification
- NEVER push if CSO returned VULNERABLE
- Always save the PR URL to the decisions log for future retros
