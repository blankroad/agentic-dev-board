---
name: agentboard-parallel-review
description: Parallel orchestrator that dispatches agentboard-cso and agentboard-redteam in parallel via the Claude Code Agent tool, then aggregates their verdicts and logs a single phase='parallel_review' decision. Use AFTER reviewer PASS, BEFORE agentboard-approval. Replaces the sequential cso → redteam chain. On any BLOCKER (CSO VULNERABLE or redteam BROKEN) it routes back to agentboard-tdd; on CLEAN it hands off to agentboard-approval.
when_to_use: Automatic after agentboard-tdd issues reviewer PASS for production-destined code. Voice triggers — "parallel review", "run cso and redteam together", "speed up review".
---

## Korean Output Style + Format Conventions (READ FIRST — applies to every user-visible output)

This skill's instructions are in English. Code, file paths, identifiers, MCP tool names, and commit messages stay English. **All other user-facing output must be in Korean**, following the rules below.

**Korean prose quality**:
- Write natural Korean. Keep only identifiers in English. Never code-switch in prose (forbidden: `important한 file을 수정합니다`, `understand했습니다`).
- Consistent sentence ending within a single response: **default to plain declarative ("~한다", "~함")** — do not mix in 존댓말 ("~합니다", "~해요"). Direct questions inside `AskUserQuestion` may use "~할까?" / "~인가?".
- Short, active-voice sentences. One sentence = one intent. No hedging ("~인 것 같습니다", "~할 수도 있을 것 같아요"). Be decisive.
- Particles (조사) and spacing (띄어쓰기) per standard Korean orthography.
- Standard IT terms (plan, scope, lock, hash, wedge, frame, gauntlet) stay in English. Do not force-translate (bad: "잠금 계획"; good: "locked plan").

**Output format**:
- Headers: `## Phase N — {Korean name}` for major phases; `### {short Korean label}` for sub-blocks. Do not append the English handle to sub-headers.
- Lists: numbered as `1.` (not `1)`); bulleted as `-` only (not `*` or `•`). No blank line between list items; one blank line between blocks.
- Identifiers and keywords use `` `code` ``. Decision labels use **bold** (max 2-3 per block — do not over-bold).
- Use `---` separators only between top-level phases, never inside a phase.

**AskUserQuestion 4-part body** (every call's question text is 3-5 lines, in this order):
1. **Re-ground** — one line stating which phase / which item is being decided.
2. **Plain reframe** — 1-2 lines describing the choice in outcome terms (no implementation jargon). Korean.
3. **Recommendation** — `RECOMMENDATION: {option label} — {one-line reason}`.
4. **Options** — short option labels in the `options` array (put detail in each option's `description` field, not in the question body).

Bounced or meta replies ("너가 정해", "추천해줘", "어떤게 좋을까?") **do not consume the phase budget** — answer inline, then immediately re-ask the same axis with tightened options.

**Pre-send self-check**: before emitting any user-visible block, verify (a) no English code-switching in prose, (b) consistent sentence ending, (c) required header is present, (d) `AskUserQuestion` body has all 4 parts. On any violation, regenerate once.

---

## Preamble — Project Guard (MANDATORY first check)

Before any other action, verify agentboard is initialized:

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
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
