---
name: agentboard-synthesize-report
description: LLM-based goal report synthesis. Reads plan.md + challenge.md + brainstorm.md + decisions.jsonl + git numstat for the target goal, dispatches the Claude Code Agent tool with a structured prompt, and writes the resulting As-Is→To-Be Markdown to `.devboard/goals/<gid>/report.md`. Non-blocking — if the Agent call fails or output fails sanity check, the skill logs a NARRATIVE_SKIPPED decision and returns without raising. Consumed by TUI Overview tab (report_md prepend) and `devboard export <gid> --source report`.
when_to_use: Automatically invoked by `agentboard-approval` right after `agentboard_generate_narrative` at Step 4.5a. May also be invoked manually by the user to regenerate a stale report. Do NOT invoke from inside TDD cycles — reports are meant for already-shipped (or about-to-ship) goals.
---

> **Language**: Respond to the user in Korean. Code, file paths, variable names, and commit messages remain English.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

- `MISSING` → print "devboard is not initialized. Run `devboard init && devboard install` first." and exit immediately.
- `OK` → proceed.

You are the **Report Synthesizer**. Your job: transform the goal's raw artifacts into a human-readable As-Is→To-Be Markdown document that leads the Overview tab and ships with `devboard export`.

## Non-blocking contract

This skill MUST NOT raise user-facing errors. Every failure mode (file missing, Agent crash, sanity-check fail) is logged as a `NARRATIVE_SKIPPED` decision and the skill returns `{status: "skipped", reason: "..."}`. The caller (`agentboard-approval`) must wrap invocation in `try/except` and continue its own flow regardless.

## Inputs (required)

- `project_root` — absolute path to the project root
- `goal_id` — the target goal id (e.g. `g_20260421_013203_33d3ef`)

Optional:
- `task_id` — if provided, decisions.jsonl and git base/head commits are scoped to that task. Otherwise the skill picks the latest task directory under the goal.

## Step 1 — Harvest artifacts

1. `plan_path = project_root / ".devboard/goals/<goal_id>/plan.md"` — read full contents
2. `challenge_path = project_root / ".devboard/goals/<goal_id>/gauntlet/challenge.md"` — read (empty string if missing)
3. `brainstorm_path = project_root / ".devboard/goals/<goal_id>/brainstorm.md"` — read (empty string if missing)
4. `decisions_path = project_root / ".devboard/goals/<goal_id>/tasks/<latest_task>/decisions.jsonl"` — load rows, compute phase totals + final verdicts (tdd_green / review / parallel_review / approval)
5. `git_stats = subprocess("git log --numstat <base>..<head>")` — compute files_changed, total adds/dels (best-effort; empty string on git failure)

Any read failure → log it internally and continue with empty string for that artifact.

## Step 2 — Build the prompt

Dispatch **one** `Agent` tool call:

```
Agent(
  description="Synthesize goal report",
  subagent_type="general-purpose",
  prompt=f"""
You are summarizing an agentboard goal for an engineering manager / teammate.
The goal has just shipped. Produce a publishable Markdown summary that a
colleague can read cold and understand: what the goal was, what changed,
whether it went well.

Inputs:

## plan.md (full)
{plan_content}

## challenge.md (known failure modes — plan risks)
{challenge_content}

## brainstorm.md (initial pain + alternatives)
{brainstorm_content}

## decision phase summary
- phase totals: {phase_counts}
- final verdicts: review={review_final}, parallel_review={parallel_final}, approval={approval_verdict}
- redteam rounds: {redteam_count} — BROKEN={broken_n}, SURVIVED={survived_n}, final={redteam_final}

## git diff numstat
{git_stats_block}

Output a Markdown document with EXACTLY these sections in order:

## 이 goal은 무엇을 개선했나
(1-paragraph plain-language summary — "previously X was broken/missing, now
Y works". 60-120 Korean words. No citation.)

## 변화 지표
| 영역 | As-Is | To-Be |
| --- | --- | --- |
| ... | ... | ... |

(3-6 rows derived from challenge.md known_failure_modes + plan.md architecture
+ diff stats. Concrete before/after cells; no "TBD" or "N/A".)

## 진행 요약
- iterations: <N>
- files changed: <N> (+<adds> −<dels>)
- review final: <verdict>
- redteam: <rounds> round(s), final <verdict>

## 배운 점 (선택)
(0-2 bullets. Include only if brainstorm/decisions surfaced a genuinely
new lesson. If nothing noteworthy, omit this entire section.)

Constraints:
- Korean for headings and body (project language).
- GitHub-flavored Markdown only — no HTML, no wrapping code fences around
  the whole document, no horizontal rules, no footnotes.
- Tables must use pipe syntax with a separator row (`| --- | --- |`).
- Do not invent information; if a field is unknown, write "(미기재)".
- Total length ≤ 800 words.
"""
)
```

## Step 3 — Sanity check

The Agent's response `text` must satisfy ALL of these structural checks before save (redteam FM#3 — pipe-count alone is trivially fooled by LLM refusals or prose with incidental `|`):

1. `len(text.strip()) >= 200` — not empty / trivial
2. Contains a **real table separator row** matching regex `^\s*\|[\s\-:|]+\|\s*$` (at least one line that looks like `| --- | --- |` — guarantees an actual pipe table, not a refusal message containing stray `|`)
3. `text.count("##") >= 2` — at least two H2 headers
4. Does NOT match any of these refusal / error patterns (case-insensitive substring): `"i cannot"`, `"i can't"`, `"i am unable"`, `"as an ai"`, `"i apologize"` — LLM refusal boilerplate
5. Does NOT contain the exact literal `(미기재)` more than 2 times — every row defaulted to unknown means the synthesize lacked real data

Failure of ANY check → write response to `.devboard/goals/<goal_id>/report_draft.md` for debug, skip main save, log `NARRATIVE_SKIPPED` decision with `reason=<rule_that_failed>`, return `{status: "skipped"}`.

## Step 4 — Save

Prepend an auto-generated timestamp + warning line to the body, then write:

```
_Auto-generated {utcnow_iso} by agentboard-synthesize-report — manual edits will be overwritten on next approval._

{text}
```

Target: `.devboard/goals/<goal_id>/report.md` (UTF-8, overwrite). Use `FileStore.atomic_write` or `Path.write_text`.

## Step 5 — Log decision

```
agentboard_log_decision(
  project_root, task_id, iter=<latest_iter>,
  phase="synthesize_report",
  reasoning="report.md generated ({len} chars, {sec}s)"  # on success
     | "synthesize skipped: <reason>"                    # on skip
  verdict_source="GENERATED" | "SKIPPED",
)
```

## Handoff

- Success: `{status: "generated", path: ".devboard/goals/<goal_id>/report.md"}` — caller continues its own flow (approval continues to Step 4.6 / converged).
- Skip: `{status: "skipped", reason: "..."}` — caller continues unchanged. The Overview tab falls back to the legacy plan_digest layout; `devboard export <gid> --source report` exits 1 with a synthesize hint.

## Common bypass attempts — NEVER allow

| User request | Correct reply |
|---|---|
| "그냥 report.md 수동으로 작성해둘게" | 자동 생성 + 덮어쓰기가 기본 — 수동 편집은 `devboard export`로 꺼낸 사본에서. 수정된 `report.md`는 다음 approval에서 덮어씀. |
| "approval 건너뛰고 여기만 돌려" | 가능. 이 skill은 manual invocation 지원 — 단, goal이 이미 lock 상태(plan.md 존재)여야 함. |

## Not your job

- DO NOT modify plan.md, plan_summary.md, brainstorm.md, challenge.md, decisions.jsonl — read-only.
- DO NOT commit or push — that's approval's domain.
- DO NOT call external APIs directly (anthropic/openai SDK) — always via the Claude Code Agent tool.
- DO NOT block approval flow — any failure must be NARRATIVE_SKIPPED + return.
