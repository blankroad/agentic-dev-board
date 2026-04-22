---
name: agentboard-parallel-review
description: Parallel orchestrator that dispatches agentboard-cso and agentboard-redteam in parallel via the Claude Code Agent tool, then aggregates their verdicts and logs a single phase='parallel_review' decision. Use AFTER reviewer PASS, BEFORE agentboard-approval. Replaces the sequential cso → redteam chain. On any BLOCKER (CSO VULNERABLE or redteam BROKEN) it routes back to agentboard-tdd; on CLEAN it hands off to agentboard-approval.
when_to_use: Automatic after agentboard-tdd issues reviewer PASS for production-destined code. Voice triggers — "parallel review", "run cso and redteam together", "speed up review".
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

## Preamble — Project Guard (MANDATORY first check)

Before any other action, verify agentboard is initialized:

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

- `MISSING` → print "agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill." and exit.
- `OK` → proceed.

You are the **Parallel Review Orchestrator**. Your job is to cut wall-clock time of the CSO + redteam review pair by dispatching both in a single message via the Claude Code `Agent` tool, then aggregating their verdicts.

## Step 0 — Pre-check auto-skip conditions

Before dispatching, decide what actually needs to run:

1. Load the current task's metadata. Let:
   - `security_sensitive_plan` = `task.metadata.security_sensitive_plan`
   - `production_destined` = `task.metadata.production_destined`
2. Run `agentboard_check_security_sensitive(diff=<current git diff>)` for a runtime check. Let `runtime_sensitive = result.sensitive`.
3. Decide per-side:
   - **CSO run?** → `cso_should_run = security_sensitive_plan OR runtime_sensitive`
   - **redteam run?** → `redteam_should_run = production_destined`
4. Branch:
   - Both false → skip both. Record `cso_verdict="SKIPPED"`, `redteam_verdict="SKIPPED"`, `overall="CLEAN"`, note="no review needed". Jump to Step 3 (log + handoff).
   - Only one is true → call that skill directly (NOT via Agent dispatch — Agent startup overhead is wasted on a single call). Record the other as `"SKIPPED"`. Jump to Step 3.
   - Both true → proceed to Step 1 (parallel dispatch).

## Step 1 — Parallel dispatch via Agent tool

Record `start_ts = time.monotonic()` (conceptually — parent agent just tracks via wall-clock).

In a **single assistant message**, emit two `Agent` tool calls (one message, two tool blocks — Claude Code treats these as independent sub-agents). Each sub-agent runs its own skill to produce a verdict and Finding list:

```
Agent(
  description="CSO security review",
  subagent_type="general-purpose",
  prompt=(
    "You are running the agentboard-cso skill. Current task_id={task_id}, run_id={run_id}, "
    "goal_id={goal_id}. Read the SKILL.md at skills/agentboard-cso/SKILL.md and execute it "
    "against the current git diff. Return a structured report with: verdict "
    "(SECURE|VULNERABLE|INCOMPLETE), and a findings list where each finding has "
    "file (str|null), line (int|null), category (e.g. 'SQLi'), "
    "category_namespace='OWASP', severity (CRITICAL|HIGH|MEDIUM), body (one-sentence summary). "
    "Cite file:line for every finding you can locate. Do NOT write to decisions.jsonl — "
    "the parent parallel-review orchestrator will log the combined outcome once."
  ),
)
Agent(
  description="Redteam adversarial review",
  subagent_type="general-purpose",
  prompt=(
    "You are running the agentboard-redteam skill. Current task_id={task_id}, run_id={run_id}, "
    "goal_id={goal_id}. Read skills/agentboard-redteam/SKILL.md and execute against the "
    "current diff. Return a structured report: verdict (SURVIVED|BROKEN|INCOMPLETE), and a "
    "findings list where each finding has file (str|null), line (int|null), category "
    "(EdgeInput|Boundary|Type|State|Concurrency|Missing), category_namespace='redteam', "
    "severity (CRITICAL|HIGH|MEDIUM), body (one-sentence summary). Do NOT write to "
    "decisions.jsonl."
  ),
)
```

Wait for BOTH sub-agents to return. Even if one returns a BLOCKER early, the Claude Code Agent tool does not support external cancellation — so you wait for both. This is the "logical early-abort" contract: wall-clock = max(cso, redteam), still strictly faster than sequential sum.

Record `end_ts`. Compute `parallel_duration_s = end_ts - start_ts`. If each sub-agent reports its own duration, use those as `cso_duration_s` and `redteam_duration_s`; otherwise approximate as `parallel_duration_s`.

## Step 2 — Aggregate & dedupe

Parse each sub-agent's verdict + findings into `agentboard.parallel.models.Finding` objects. Then call the pure functions:

```python
from agentboard.parallel import dedupe_findings, aggregate_verdict

report = dedupe_findings(cso_findings, redteam_findings)
verdict = aggregate_verdict(cso=cso_verdict, redteam=redteam_verdict)
```

- `report.findings` — combined, deduped, higher-severity-kept on same-namespace collisions.
- `report.overlap_count` — how many pairs collapsed.
- `verdict.status` ∈ {CLEAN, BLOCKER, BOTH_BLOCKER, INCOMPLETE}.
- `verdict.reasons` ∈ subset of {cso, redteam}.

## Step 3 — Log + checkpoint

Call the MCP tool exactly once:

```
agentboard_log_parallel_review(
  project_root=<path>,
  task_id=<task_id>,
  iter=<current_iter>,
  cso_verdict=<"SECURE"|"VULNERABLE"|"INCOMPLETE"|"SKIPPED">,
  redteam_verdict=<"SURVIVED"|"BROKEN"|"INCOMPLETE"|"SKIPPED">,
  overall=<verdict.status>,
  parallel_duration_s=<float>,
  cso_duration_s=<float>,
  redteam_duration_s=<float>,
  overlap_count=<report.overlap_count>,
  reasoning=<one-line summary>,
)
```

Then a single checkpoint:

```
agentboard_checkpoint(project_root, run_id, "parallel_review_complete", {
  overall: verdict.status,
  cso_verdict, redteam_verdict, overlap_count,
  parallel_duration_s, cso_duration_s, redteam_duration_s,
})
```

## Step 4 — Handoff

Branch on `verdict.status`:

| Status | Action |
|---|---|
| `CLEAN` | Invoke `agentboard-approval` via Skill tool. |
| `BLOCKER` | Write a failing test reproducing the most severe finding, invoke `agentboard-tdd` with that RED as the next step. |
| `BOTH_BLOCKER` | Same as BLOCKER but pick the higher-severity finding across both lists. |
| `INCOMPLETE` | Report the crash, do NOT proceed to approval, ask the user whether to retry parallel-review or fall back to sequential cso → redteam. |

## Measurement discipline

The whole point of this skill is wall-clock improvement. After each run, compare `parallel_duration_s` against the rough sum `cso_duration_s + redteam_duration_s`. If over 3 real runs the ratio `parallel_duration_s / (cso_duration_s + redteam_duration_s) > 0.9`, the Claude Code runtime is likely serializing the Agent calls and this approach is not buying time — escalate to the user and re-evaluate Approach B vs. plain sequential.

## Not your job

- Do NOT rewrite CSO or redteam findings. You aggregate, you do not reinterpret.
- Do NOT push. That is `agentboard-approval`.
- Do NOT silently drop an INCOMPLETE — always surface it to the user.
