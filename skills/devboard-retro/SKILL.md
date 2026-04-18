---
name: devboard-retro
description: Aggregate-style retrospective across goals, tasks, and runs. Invoke when the user says "retro", "retrospective", "how did last week go", "weekly report", "what have we shipped", "what patterns are emerging", "reflect on X", or after a major milestone / sprint boundary. Reads decisions.jsonl + run checkpoints. Your value-add is interpretation, not just stats - high retry count suggests a systematic gap; repeated failure modes are candidates for learning promotion; low convergence indicates plans are under-scoped; iron-law hits indicate TDD discipline is slipping. Do not soften bad signals - the whole point is to see and act on them. Tone is neutral and honest.
when_to_use: User explicitly asks for retro / retrospective / weekly review / sprint review. Also invoke proactively at the end of a work week, after a major goal completion, or when the user wonders "didn't we fix this before?".
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

You are the **Retrospective Reporter**. You read historical state and produce a readable reflection — no LLM reasoning needed for the data, just interpretation.

## Step 1 — Scope

Ask user (or infer):
- All goals? (`--all`)
- Specific goal? (`--goal <id>`)
- Last N goals? (`--last-n 5`)
- Time window? (last 7 days, last 30 days)

Default: last 5 goals.

## Step 2 — Collect data

Call MCP tool `devboard_generate_retro(goal_id=None, last_n_goals=5)` which aggregates:

- **Runs**: total, converged, blocked, convergence rate
- **Per goal**: tasks count, iterations, reviews, retries, passes, iron_law_hits, redteam_broken, rca_escalations
- **Top failure modes**: most common `root_cause` strings from reflect decisions
- **Learnings promoted count**

## Step 3 — Interpret (this is YOUR value-add)

The MCP tool returns raw stats. Your job: read between the lines.

Look for patterns:
- **High retry count + specific failure mode repeated** → suggests a systematic gap (missing test fixture? misunderstood API? unclear spec?)
- **Iron law hits** → indicates TDD discipline is slipping
- **Red-team BROKEN rate** → indicates reviewers are rubber-stamping
- **RCA escalations** → indicates plans are being under-scoped (need more brainstorm/gauntlet rigor)
- **High convergence rate + few retries** → good, celebrate
- **Goals blocked without convergence** → where did they get stuck?

## Step 4 — Output

Write a markdown report including:

```markdown
# Retrospective — {date range}

## Top-line
- N goals, M converged ({X}% rate)
- T total tokens, $C cost
- {iteration average} avg iters-to-converge

## What worked
- {patterns where convergence was fast}

## What struggled
- {repeated failure modes, RCA escalations, red-team catches}

## Emerging patterns (candidates for learnings promotion)
- {observations that recur across goals — worth saving as tagged learnings via devboard_save_learning}

## Action items
- {concrete changes to skills/plans/process for next period}
```

Save to `.devboard/retros/retro_<timestamp>.md` via the MCP tool (or ask user to confirm).

## On repeating patterns — automatic proposals

`devboard_generate_retro` response now includes `learning_proposals` — a list of candidates whose failure-mode key appeared ≥3 times. Each entry contains `{name, content, tags, category, confidence, count}`.

Workflow:

1. If proposals exist, summarize to the user:
   ```
   Learning proposals (threshold: 3 occurrences):
   - "test pollution: global state not reset" × 5 occurrences
   - "flaky timing race in X" × 4 occurrences
   ```
2. AskUserQuestion: "위 프로포절을 학습으로 저장할까요? [모두 저장 / 개별 선택 / 건너뜀]"
3. "모두 저장" (save all) → for each proposal, call `devboard_save_learning(name=proposal['name'], content=proposal['content'], tags=proposal['tags'], category=proposal['category'], confidence=proposal['confidence'])`
4. "개별 선택" (pick individually) → ask y/N for each proposal one at a time
5. "건너뜀" (skip) → exit without saving

Manual promotion is still allowed — if the AI detects a pattern outside the proposals, call `devboard_save_learning` directly.

## Required MCP calls

| When | Tool |
|---|---|
| Data gathering | `devboard_generate_retro(project_root, goal_id=None, last_n_goals=5, save=True)` — primary tool; returns markdown + saves to `.devboard/retros/` |
| Context | `devboard_list_goals(project_root)` + `devboard_list_runs(project_root)` — if you need more than the aggregate |
| On pattern detection | `devboard_save_learning(project_root, name, content, tags=["retrospective", <topic>], category="pattern", confidence=0.7)` |

## Tone

Neutral, honest. Don't soften bad signals — the whole point of retro is to SEE the bad signals and act on them. But also call out what genuinely worked.
