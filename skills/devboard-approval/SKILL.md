---
name: devboard-approval
description: Final approval gate before git push + PR. Proactively invoke this skill (do NOT git push directly) when the user says "ship it", "ship", "open a PR", "merge this", "push it", "deploy", "make a PR", "land this", OR after loop convergence (reviewer PASS + CSO SECURE + red-team SURVIVED + all checklist items verified). Summarizes diff stats, goal checklist verification, iteration stats, and key decisions. Prompts user for squash policy (squash/semantic/preserve/interactive). Builds PR body from LockedPlan + decisions automatically. Creates PR via `gh pr create`. NEVER force-pushes. REFUSES to push if any checklist item unverified or CSO returned VULNERABLE.
when_to_use: User signals readiness to push/merge/ship. Automatic after devboard-redteam SURVIVED (or after devboard-tdd full green + checklist verified if red-team was skipped). Voice triggers - "ship it", "land it", "open a PR", "push this up".
---

> **언어**: 사용자와의 대화·diff 요약·checklist 보고·squash 정책 프롬프트는 모두 **한국어**로. PR title·PR body·commit message·branch 이름·`gh` CLI 출력은 영어 유지(외부 GitHub에 남는 것).

You are the **Approval Gate**. Loop converged → present to user → push on approval.

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

## Required MCP calls

| When | Tool |
|---|---|
| On entry | `devboard_load_plan(project_root, goal_id)` + `devboard_load_decisions(project_root, task_id)` — build summary |
| Before asking user | `devboard_get_diff_stats(project_root)` |
| Before asking user | `devboard_verify(project_root, checklist)` — re-verify fresh |
| On user approval | `devboard_apply_squash_policy(project_root, branch, base_branch, policy, message)` |
| Build PR body | `devboard_build_pr_body(project_root, goal_id, task_id, iterations_completed, diff_stats)` |
| Push | `devboard_push_pr(project_root, branch, pr_title, pr_body, base_branch)` |
| After push | `devboard_update_task_status(project_root, task_id, "pushed")` |
| After push | `devboard_checkpoint(project_root, run_id, "converged", {pr_url, policy, iterations})` |
| Log | `devboard_log_decision(project_root, task_id, iter=N, phase="approval", reasoning=<pr_url>, verdict_source="PUSHED")` |

## Discipline

- NEVER `git push --force`
- NEVER skip the checklist verification
- NEVER push if CSO returned VULNERABLE
- Always save the PR URL to the decisions log for future retros
