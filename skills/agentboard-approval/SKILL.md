---
name: agentboard-approval
description: Final approval gate before git push + PR. Proactively invoke this skill (do NOT git push directly) when the user says "ship it", "ship", "open a PR", "merge this", "push it", "deploy", "make a PR", "land this", OR after loop convergence (reviewer PASS + CSO SECURE + red-team SURVIVED + all checklist items verified). Summarizes diff stats, goal checklist verification, iteration stats, and key decisions. Prompts user for squash policy (squash/semantic/preserve/interactive). Builds PR body from LockedPlan + decisions automatically. Creates PR via `gh pr create`. NEVER force-pushes. REFUSES to push if any checklist item unverified or CSO returned VULNERABLE.
when_to_use: User signals readiness to push/merge/ship. Automatic after agentboard-redteam SURVIVED (or after agentboard-tdd full green + checklist verified if red-team was skipped). Voice triggers - "ship it", "land it", "open a PR", "push this up".
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
   - If missing, **refuse**: "TDD가 완료되지 않았습니다. agentboard-tdd를 먼저 실행하세요." → exit skill
2. **Review gate — parallel_review (1st priority / preferred) OR legacy cso+redteam (fallback)**:
   - **1순위 (preferred)**: a single `phase="parallel_review"` entry (produced by agentboard-parallel-review) — if present, read its `metadata.overall`:
     - `overall="CLEAN"` → pass this gate (no need to also check cso/redteam)
     - `overall ∈ {"BLOCKER", "BOTH_BLOCKER"}` → **refuse**: "parallel-review returned {overall}. agentboard-tdd로 복귀." → exit skill
     - `overall="INCOMPLETE"` → **refuse**: "parallel-review returned INCOMPLETE. 재시도 필요." → exit skill
   - **Legacy fallback (backward compat)**: if NO `phase="parallel_review"` entry exists, fall back to checking the separate `phase="cso"` + `phase="redteam"` pair:
     - If the diff or LockedPlan contains security-sensitive keywords (auth, password, token, crypto, SQL, subprocess, eval, exec), verify a `phase="cso"` entry exists.
       - Missing → **refuse**: "보안 민감 변경이 감지됐으나 CSO 검토가 없습니다. agentboard-cso 또는 agentboard-parallel-review를 먼저 실행하세요." → exit skill
     - If a `phase="cso"` entry exists and its `verdict_source="VULNERABLE"`, **refuse**: "CSO returned VULNERABLE. 이슈 해결 후 재시도." → exit skill
     - The legacy `phase="redteam"` entry is optional unless the task is production-destined (see task.metadata).
3. **Dep audit check** — call `devboard_check_dependencies(project_root)`.
   - If `skipped_reason` is set → pass (audit unavailable)
   - If `severity_counts.CRITICAL ≥ 1` or `severity_counts.HIGH ≥ 1` → **refuse**: "Dep audit VULNERABLE: CRITICAL={c}, HIGH={h}. agentboard-dep-audit를 실행해서 세부 확인 후 업그레이드 필요." → exit skill
   - Otherwise → pass

If all three conditions pass (TDD complete + review gate + dep audit), proceed to Step 1.

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
3. Write the Outcome section to `plan.md` (see Step 4.5 below)
4. Mark the task as pushed (Step 4.5 handoff — see below)
5. Report the PR URL to the user

## Step 4.5 — Write Outcome section to plan.md (MANDATORY)

After `devboard_push_pr` returns success (or a direct-push equivalent completes), first auto-regenerate `plan_summary.md` when the task is UI-surface, then write the publishable Outcome block to the goal's `plan.md` so the document records "what actually happened" next to the original plan.

### Step 4.5a — Auto-regenerate plan_summary.md narrative (if `ui_surface`)

When `task.metadata.get("ui_surface", False)` is True, call `devboard_generate_narrative` to refresh `.devboard/goals/<goal_id>/plan_summary.md` BEFORE the Outcome write (so the narrative covers the final push state). Wrap the call in `try/except` — generator failure is non-blocking: log a `NARRATIVE_SKIPPED` decision and continue.

```python
task_meta = task.metadata or {}
if task_meta.get("ui_surface", False):
    try:
        narrative = devboard_generate_narrative(
            project_root=project_root,
            goal_id=goal_id,
        )
        # narrative = {"plan_summary_path": ..., "section_citation_counts": ..., "total_citations": ...}
    except Exception as exc:
        devboard_log_decision(
            project_root, task_id, iter=iteration,
            phase="approval",
            reasoning=f"narrative generation skipped: {exc!r}",
            verdict_source="NARRATIVE_SKIPPED",
        )
```

### Step 4.5a.2 — Auto-invoke `agentboard-synthesize-report` (ALL goals)

After `devboard_generate_narrative` (regardless of `ui_surface`), invoke the `agentboard-synthesize-report` skill via the `Skill` tool so the goal ships with a publishable `.devboard/goals/<goal_id>/report.md` (As-Is → To-Be summary, consumed by TUI Overview tab + `devboard export <gid> --source report`).

The synthesize skill is **non-blocking** by contract: it catches its own failures and logs `NARRATIVE_SKIPPED`. Wrap the Skill call in `try/except` here too so the approval flow never stalls on a missing/broken agent response.

```
try:
    Skill(
        skill="agentboard-synthesize-report",
        args=f"goal_id={goal_id} task_id={task_id}",
    )
    # Skill writes report.md on success OR logs NARRATIVE_SKIPPED and returns silently.
except Exception as exc:
    devboard_log_decision(
        project_root, task_id, iter=iteration,
        phase="approval",
        reasoning=f"synthesize-report hook skipped: {exc!r}",
        verdict_source="NARRATIVE_SKIPPED",
    )
```

Failure of this hook MUST NOT block Step 4.5b (Outcome), Step 4.6 (TTY smoke), converged checkpoint, or `task.status=pushed`.

### Step 4.5b — Write Outcome section

```python
from devboard.docs.plan_sections import PlanSection, upsert_plan_section
from pathlib import Path

plan_path = Path(project_root) / ".devboard" / "goals" / goal_id / "plan.md"
outcome = (
    f"- Status: pushed\n"
    f"- Final commit: {final_commit_sha}\n"
    f"- PR: {pr_url or 'direct push to origin/main'}\n"
    f"- Iterations: {iterations}\n"
    f"- Tests: {tests_total} passing\n"
    f"- Red-team: {redteam_rounds} rounds, final {redteam_final_verdict}\n"
    f"- CSO: {cso_verdict or 'not required'}\n"
    f"- Pushed at: {utcnow_iso}"
)
upsert_plan_section(plan_path, PlanSection.OUTCOME, outcome)
```

The helper is idempotent — re-running approval after a fix produces the same single-section result, no stacking. The `plan.json` locked_hash is unaffected (Outcome lives in plan.md only).

After this write, continue to Step 4.6 (real-TTY screenshot for UI tasks), then `devboard_checkpoint "converged"` and `devboard_update_task_status status="pushed"`.

## Step 4.6 — Capture real-TTY smoke for UI tasks (if `ui_surface` set)

When the current task's metadata has `ui_surface=True` (gauntlet sets this during Finalize when arch.md / decide.json mention TUI / widget / pilot / textual / ui / frontend / browser keywords), run the real-TTY smoke tool AFTER Outcome has been written, and record any capture into the `## Screenshots / Diagrams` section of plan.md:

```python
task_meta = task.metadata or {}
if task_meta.get("ui_surface", False):
    # Run real-TTY smoke
    result = devboard_tui_render_smoke(project_root, timeout_s=3.0)

    # Graceful skip if pty/devboard unavailable — no Screenshots block
    if "skipped_reason" in result:
        # Log for visibility; do NOT write an empty section
        print(f"[screenshots] skipped: {result['skipped_reason']}")
    else:
        from devboard.mcp_tools.capture_store import save_tui_capture
        from devboard.docs.plan_sections import PlanSection, upsert_plan_section
        from pathlib import Path

        capture_path = save_tui_capture(project_root, goal_id, result)
        rel = capture_path.relative_to(Path(project_root))
        screenshots_body = (
            f"### TUI real-TTY capture ({capture_path.stem})\n"
            f"- Path: `{rel}`\n"
            f"- Result: mounted={result.get('mounted')}, "
            f"crashed={result.get('crashed')}, "
            f"captured_bytes={result.get('captured_bytes')}, "
            f"duration_s={result.get('duration_s')}"
        )
        plan_path = Path(project_root) / ".devboard" / "goals" / goal_id / "plan.md"
        upsert_plan_section(plan_path, PlanSection.SCREENSHOTS, screenshots_body)
```

For non-UI tasks (`ui_surface` missing or `False`), this step is a no-op — use `.get("ui_surface", False)` so legacy tasks without the marker default to skip. Idempotent: re-running approval regenerates a fresh capture file (new timestamp) and REPLACES the `## Screenshots / Diagrams` section (single-block, not cumulative).

## Failure modes

- **Push fails**: network / auth issues. Report error. Task remains in `awaiting_approval`.
- **gh not installed**: fall back — push only, tell user to open PR manually with the pre-built body.
- **Checklist has ✗ items**: refuse to push. Hand back to `agentboard-tdd`.
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

---

## UI Preview integration (when ui_surface=True)

Before `git push` and BEFORE PR body assembly, if `task.metadata.ui_surface == True`, invoke `agentboard-ui-preview` via the Skill tool with `layer=2`. That skill calls `devboard_tui_capture_snapshot` with `include_svg=True` and writes both text + SVG frames under `.devboard/tui_snapshots/<goal_id>/layer2/`. The resulting paths are stamped into plan.md's `## Screenshots / Diagrams` section and referenced from the PR body so reviewers see the visual change before merging.

If the goal's directory contains `scenes.yaml`, run Layer 3: iterate every declared scene (`scene_id`, `keys`, `description`, `tags`) and capture one SVG per entry. Link every scene's SVG in the PR body with the scene description as caption.

Refuse to push when any Layer 2/3 capture returns `crashed=True` — surface the traceback and route back to `agentboard-rca`.

Skip entirely when `ui_surface=False`. The legacy `devboard_tui_render_smoke` (crash gate) still runs independently.
