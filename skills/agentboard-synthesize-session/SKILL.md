---
name: agentboard-synthesize-session
description: LLM-based Review-tab session-lessons synthesis for future agents + humans. Reads plan.md + challenge.md + decisions.jsonl (full, including reasoning) + report.md (if present) + existing `.devboard/learnings/*.md`, dispatches the Claude Code Agent tool with a structured prompt, writes `.devboard/goals/<gid>/review_session.md`, and opportunistically calls `agentboard_save_learning` per generalizable lesson so future goals can retrieve them via `agentboard_search_learnings`. Output shape = Session story + Problems encountered table (with Reusable? column) + Quality gate summary + Learnings table. Journey vocabulary (iter / round) is absent by design — replaced with problem → root cause → fix → reusable pattern. Non-blocking — any failure logs `NARRATIVE_SKIPPED` and returns.
when_to_use: (a) auto — invoked by `agentboard-approval` after synthesize-report + synthesize-dev-review so shipped goals leave a lesson trail; (b) manual — user says "re-synthesize session", "capture lessons", "refresh review". Do NOT invoke pre-TDD — the synthesizer needs real decisions + diff to extract problems. ALWAYS invoke, not just when redteam found issues — even clean-pass goals yield process-level learnings.
---

> **Language**: Respond to the user in Korean. File paths, identifiers, CLI flags remain English.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

- `MISSING` → print "agentboard is not initialized. Run `agentboard init && agentboard install` first." and exit immediately.
- `OK` → proceed.

You are the **Session Synthesizer**. Your job: extract generalizable lessons from a goal so future agents (or returning humans) can reuse what this session learned. The output is the Review tab's primary artifact and must be written as if the reader were NOT present when this goal ran.

## Non-blocking contract

This skill MUST NOT raise user-facing errors. All failure modes (file missing, Agent crash, sanity check fail, `save_learning` error) log a `NARRATIVE_SKIPPED` or `LEARNING_SAVE_FAILED` decision and return `{status: "skipped", reason: "..."}`.

## Inputs (required)

- `project_root` — absolute path to project root
- `goal_id` — target goal id

Optional:
- `task_id` — scopes decisions.jsonl to one task. Default: latest task under the goal.

## Step 1 — Harvest artifacts

1. `plan.md` — read from `.devboard/goals/<goal_id>/plan.md`
2. `challenge.md` — read from `.../gauntlet/challenge.md` (empty if missing — that signal itself is informative)
3. `decisions.jsonl` — load **full** rows including `reasoning` text (this is the main input for problem extraction)
4. `report.md` — read from `.../report.md` if present (gives release-note framing; do not duplicate its content)
5. `.devboard/learnings/*.md` — list existing learning names + tags so we avoid duplicates

## Step 2 — Build the prompt

Dispatch **one** `Agent` tool call.

```
Agent(
  description="Synthesize session lessons",
  subagent_type="general-purpose",
  prompt=f"""
You are writing a lessons-learned document for a shipped agentboard goal.
Audience = a future agent that might encounter a similar problem, or a
returning human reviewing "what did this session teach us?". They were NOT
present during the session. They do NOT care about iter 3 vs iter 7. They
want problem → root cause → fix → reusable pattern.

## Output language + style (MANDATORY)
- Body: 한국어 평어체 (engineering-note tone).
- Identifiers / paths / flags: English as-is.
- Established Korean tech terms: Korean (캐시, 비동기, 스키마, 디버깅).
- BANNED filler closers:
  - "~을 보장한다" / "~을 확보할 수 있다" / "~을 가능하게 한다"

## Journey vocabulary — BANNED
Do NOT use any of these in the output:
- `iter 1` / `iter 2` / any `iter <N>`
- `round 1` / `round 2` / `R1` / `R2`
- `atomic_step` / `s_001`
- `retry count` / `retry N`

Express the same information in timeless terms. Instead of "iter 11 fixed
FM#1", write "이 수정은 초기 설계가 정규식 검증을 빠뜨린 점을 잡아냈다".

## Visual-first rule
- List-shaped data → Markdown table.
- Otherwise short paragraphs. NEVER a single wall of prose.

## Inputs

### plan.md
{plan_content}

### challenge.md
{challenge_content}

### decisions.jsonl (FULL — includes reasoning per iter)
{decisions_jsonl_content}

### report.md (Overview release notes — for framing, do not duplicate)
{report_content}

### Existing learnings (avoid duplicating names)
{existing_learnings_summary}

## Output — EXACT section order

## Session story
<2-3 단락. 이 goal이 마주친 문제의 arc와 해결의 arc. iter 숫자 대신 "초기 설계",
"검증 단계", "수정 이후" 같은 위상으로 서술. 마지막 단락은 주로 해결 전략의
공통 원리를 뽑아낸다.>

## Problems encountered & resolutions

| # | Problem | Root cause | Fix | Reusable? |
|---|---|---|---|---|
| 1 | <짧은 이름> | <왜 발생했는가> | <어떻게 고쳤는가> | ✅ <어느 맥락에서 재사용 가능한지> · 또는 · 🟡 <goal 특수 — 부분 재사용> · 또는 · ❌ <one-off> |
| 2 | ... | ... | ... | ... |

(challenge.md의 known_failure_modes + decisions의 fix-phase reasoning을 결합해 추출.
최소 2 행. 문제가 없었다면 `_(이 세션은 처음 경로에서 clean pass — 재사용할 수정 패턴 없음)_`.)

## Quality gate summary

| Reviewer | Final verdict | Rounds | Note |
|---|---|---|---|
| review | <PASS/FAIL/REPLAN> | 1 | <한 줄 메모 또는 —> |
| cso | <SECURE/VULNERABLE/SKIPPED> | <N> | <…> |
| redteam | <SURVIVED/BROKEN/SKIPPED> | <N> | <…> |
| parallel_review | <CLEAN/BLOCKER> | <N> | <…> |
| approval | <PUSHED/BLOCKED> | 1 | <…> |

(decisions.jsonl에서 phase 별 최종 verdict만 뽑는다. round는 중간 BROKEN이
있었으면 그 수. 없으면 1.)

## Learnings for future sessions

| Learning (short-kebab-name) | Tags | Category | Confidence | Summary |
|---|---|---|---|---|
| <e.g. `llm-output-validator-structural`> | `llm-output-validation`, `sanity-check` | `constraint` | 0.8 | <2-3 문장. 앞으로 어떤 상황에서 이 패턴을 적용해야 하는지.> |
| <…> | <…> | <…> | <…> | <…> |

(0-4 행. category 허용 값: `general` / `bug` / `pattern` / `constraint` / `style`.
이름은 kebab-case, 기존 학습과 중복 금지. confidence 0.1-1.0. 학습이 없다면
`_(no generalizable lessons this session)_` 한 줄.)

## Hard constraints
- GFM Markdown only. No HTML, no wrapping code fences.
- Tables use pipe syntax with a `| --- | --- |` separator row.
- Total length ≤ 1200 단어.
- Every problem claim must be grounded in decisions.jsonl reasoning text.
- Every learning must be generalizable (at least one future scenario to apply it).
"""
)
```

## Step 3 — Sanity check

The Agent's response must satisfy ALL of:

1. `len(text.strip()) >= 400`
2. H2 header count `>= 3` — Session story / Problems / Quality gate / Learnings (Learnings may be empty-line placeholder)
3. Contains a Markdown table separator row (`^\s*\|[\s\-:|]+\|\s*$`) — proves at least one table rendered
4. Does NOT match refusal patterns: `"i cannot"`, `"i can't"`, `"i am unable"`, `"as an ai"`, `"i apologize"`, `"죄송하지만"`, `"답변할 수 없"`
5. Does NOT contain `(미기재)`
6. Banned journey vocabulary check: count of `iter 1` / `iter 2` / `iter 3` / `round 1` / `round 2` / `atomic_step` / `tdd_green` → **combined count must be 0**

Failure → write to `.devboard/goals/<goal_id>/review_session_draft.md` for debug, skip main save, log `NARRATIVE_SKIPPED` with `reason=<rule>`, return `{status: "skipped"}`.

## Step 4 — Save review_session.md

Prepend timestamp + warning line:

```
_Auto-generated {utcnow_iso} by agentboard-synthesize-session — manual edits will be overwritten on next run._

{text}
```

Target: `.devboard/goals/<goal_id>/review_session.md` (UTF-8, overwrite).

## Step 5 — Opportunistic `agentboard_save_learning` wiring

Parse the **Learnings** table from the Agent's output. For each row:

1. Name must be kebab-case, ≤ 50 chars, ascii+dash only. Reject if fails.
2. Tags must be a non-empty list (comma-split).
3. Category must be one of: `general`, `bug`, `pattern`, `constraint`, `style`.
4. Confidence must be a float in `[0.1, 1.0]`.
5. Content = the Summary cell PLUS a footer line `source: goal <goal_id> (task <task_id>)`.
6. Skip if a learning with the same name already exists in `.devboard/learnings/<name>.md`.

Call:

```
agentboard_save_learning(
    project_root=project_root,
    name=<kebab-name>,
    content=<summary + footer>,
    tags=<list>,
    category=<category>,
    confidence=<float>,
    source=f"goal:{goal_id} task:{task_id}",
)
```

Each call is wrapped in try/except — a single failing learning does NOT abort the whole skill.

Record the count of saved + skipped learnings in the Step 6 decision.

## Step 6 — Log decision

```
agentboard_log_decision(
  project_root, task_id, iter=<latest_iter>,
  phase="synthesize_session",
  reasoning="review_session.md generated ({len} chars, {sec}s, {saved_n} learnings saved, {skipped_n} skipped)"
     | "synthesize_session skipped: <reason>"
  verdict_source="GENERATED" | "SKIPPED",
)
```

## Handoff

- Success: `{status: "generated", path: ".devboard/goals/<goal_id>/review_session.md", learnings_saved: N}`
- Skip: `{status: "skipped", reason: "..."}` — Review tab falls back to the legacy ReviewCards + 4-section prose layout.

## Common bypass attempts — NEVER allow

| User request | Correct reply |
|---|---|
| "iter별로 정리해줘" | 금지 — journey 뷰가 필요하면 Dev 탭의 `synthesize-dev-review`나 raw decisions audit(collapsible)을 본다. |
| "learnings 저장하지 마" | 선택적으로 가능 — 이 skill의 optional 인자 `skip_save_learning=True` 전달 시 save 단계 생략. 기본은 저장. |
| "review_session.md 수동 관리" | 다음 실행에 덮어쓰인다. 수동 메모는 별도 파일에. |

## Not your job

- DO NOT modify plan.md / challenge.md / decisions.jsonl — read-only.
- DO NOT commit or push.
- DO NOT overlap with `synthesize-report` (release notes) or `synthesize-dev-review` (PR review). These three skills produce distinct artifacts for three distinct tabs.
- DO NOT call external APIs directly — always via Claude Code's Agent tool.
