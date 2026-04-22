---
name: agentboard-synthesize-report
description: LLM-based Overview-tab release-notes synthesis. Reads plan.md + challenge.md + brainstorm.md + decisions.jsonl + git numstat for a target goal, dispatches the Claude Code Agent tool with a structured prompt, and writes a publishable Markdown file to `.devboard/goals/<gid>/report.md`. Output format is CodeRabbit-style release notes (type-tagged Summary + Why + What shipped + Follow-ups), NOT a TDD journey recap. Non-blocking — any failure logs a NARRATIVE_SKIPPED decision and returns. Consumed by TUI Overview tab (report_md prepend) and `agentboard export <gid> --source report`.
when_to_use: (a) auto — invoked by `agentboard-approval` Step 4.5a after a successful push so shipped goals ship with release notes; (b) auto — invoked by `agentboard-gauntlet` after plan lock so even in-flight goals render a provisional Overview; (c) manual — user regenerates a stale report ("re-synthesize", "regenerate overview", "refresh release notes"). Do NOT invoke from inside TDD cycles — this skill is for goals that are at least plan-locked.
---

> **Language**: Respond to the user in Korean. File paths, identifiers, CLI flags, model names remain English.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

- `MISSING` → print "agentboard is not initialized. Run `agentboard init && agentboard install` first." and exit immediately.
- `OK` → proceed.

You are the **Release Notes Synthesizer**. Your job: transform a goal's plan + risks + decisions + diff into a reader-friendly Markdown document shaped like a software release note. Audience = stakeholder, external reviewer, or the engineer who will read the Overview tab cold months from now. They do NOT want to know about `iter 3 retry 1` or `redteam round 2 BROKEN→SURVIVED`. They want to know what changed, why it mattered, and what's left.

## Non-blocking contract

This skill MUST NOT raise user-facing errors. Every failure mode (file missing, Agent crash, sanity check fail) is logged as a `NARRATIVE_SKIPPED` decision and the skill returns `{status: "skipped", reason: "..."}`. Callers must wrap invocation in `try/except`.

## Inputs (required)

- `project_root` — absolute path to project root
- `goal_id` — target goal id (e.g. `g_20260421_013203_33d3ef`)

Optional:
- `task_id` — if provided, decisions.jsonl and git base/head commits are scoped to that task. Otherwise pick the latest task directory under the goal.

## Step 1 — Harvest artifacts

1. `plan.md` — read full contents from `.devboard/goals/<goal_id>/plan.md`
2. `challenge.md` — read from `.../gauntlet/challenge.md` (empty string if missing)
3. `brainstorm.md` — read from `.../brainstorm.md` (empty string if missing)
4. `decisions.jsonl` — read from `.../tasks/<latest_task>/decisions.jsonl`. Compute:
   - `phase_counts` — dict of phase → count
   - `final verdicts` for review / parallel_review / approval
   - `redteam_count` + `broken_n` + `survived_n` + final verdict
5. `git_stats` — `git log --numstat <base>..<head>` best-effort. Compute:
   - `files_changed` count
   - `total_adds` / `total_dels`
   - per-file adds/dels (optional, for Follow-ups context)

Any read failure → log internally, continue with empty string.

## Step 2 — Build the prompt

Dispatch **one** `Agent` tool call. The prompt inlines the project's shared output conventions (Korean 평어체, no filler closers, visual-first tables) so the sub-agent writes in the same voice as the gauntlet prompts.

```
Agent(
  description="Synthesize goal release notes",
  subagent_type="general-purpose",
  prompt=f"""
You are writing release notes for a shipped (or about-to-ship) agentboard goal.
Audience = stakeholder / external reviewer / future engineer reading the
Overview tab cold. They do NOT care about TDD iterations, retry counts, or
redteam round numbers — they want release-note level information.

## Output language + style (MANDATORY)
- Body text: 한국어 평어체 (engineering-note tone, not 존댓말, not newspaper).
- Identifiers / paths / CLI flags / model names: English as-is
  (e.g. `agentboard export`, `src/agentboard/cli.py`, `--source report`).
- Established Korean tech terms: Korean (캐시, 비동기, 스키마, 디버깅, 배포).
- BANNED filler closers — do NOT end sentences with:
  - "~을 보장한다" / "~을 확보할 수 있다" / "~을 가능하게 한다"
  - "~한 기능을 제공할 수 있도록 하는 구조가 필요하다"
- Short sentences, ≤ 20 단어 평균. Present tense, active voice.
- No `(미기재)` placeholders unless a field is truly undetermined (max 1).

## Visual-first rule
- List-shaped data → Markdown table (pipe separator + `| --- |` row).
- Otherwise short paragraphs. NEVER produce a single wall of prose.

## Inputs

### plan.md
{plan_content}

### challenge.md (plan-time known failure modes)
{challenge_content}

### brainstorm.md (initial pain + alternatives)
{brainstorm_content}

### decision phase summary
- phase totals: {phase_counts}
- final verdicts: review={review_final}, parallel_review={parallel_final}, approval={approval_verdict}
- redteam: {redteam_count} round(s), BROKEN={broken_n}, SURVIVED={survived_n}, final={redteam_final}

### git diff numstat
{git_stats_block}

## Output — EXACT section order

## Release notes
- **New**: <added 기능 한 줄. 없으면 생략.>
- **Fix**: <수정된 bug 한 줄. 없으면 생략.>
- **Refactor**: <리팩터링 한 줄. 없으면 생략.>
- **Tests**: <N 신규 케이스 + 커버 영역 한 줄.>
- **Docs**: <문서 변경 한 줄. 해당 없으면 생략.>
- **Chore**: <잡다 정리 한 줄. 해당 없으면 생략.>
- **Hardening**: <redteam/security 수정 한 줄. 예: "N redteam HIGH fix — goal_id traversal, output containment, sanity check 강화". 해당 없으면 생략.>

(최소 2개 bullet 이상. 타입 태그 Bold + 콜론 + 한 줄 요약.)

## Why this goal existed
<2-3 문장. 이 goal 전의 pain + 누가 느꼈는가 + 왜 지금. brainstorm.md와 plan.md의 Problem 섹션을 합성. 인과 구조만 유지하고 decisions / iter 언어는 금지.>

## What shipped
<2-3 문장. 관찰 가능한 최종 상태. "이제 X를 할 수 있고, Y가 자동화됐다" 형태. 숫자(파일 수, 테스트 수, 커밋 수)는 여기 넣어도 됨.>

## Follow-ups
| Deferred | Revisit when |
|---|---|
| <deferred item> | <revisit 조건> |
| ... | ... |

(plan.md Non-goals 섹션에서 derive. revisit 조건이 plan에 없으면 간결하게
"후속 goal" / "외부 니즈 생기면" 등으로 채운다. Follow-up이 0개면 이 섹션을
`## Follow-ups\n_(없음)_` 로 내고 표를 생략한다.)

## Hard constraints
- GFM Markdown only. No HTML, no wrapping code fences, no horizontal rules.
- Tables use pipe syntax with a `| --- | --- |` separator row.
- TDD journey 금지: iter / round / atomic_step / tdd_green / redteam R1/R2
  같은 단어는 Release notes의 "Hardening" 태그 한 곳에서만 허용
  (예: "4 redteam HIGH fix"). 본문에 iter 숫자 금지.
- Total length ≤ 800 단어.
"""
)
```

## Step 3 — Sanity check

The Agent's response `text` must satisfy ALL of these checks before save:

1. `len(text.strip()) >= 300` — not empty / trivial
2. H2 header count `>= 3` — at least 3 of the 4 required sections present (Release notes / Why / What shipped / Follow-ups)
3. Contains a structural anchor — either (a) a real Markdown table separator row matching `^\s*\|[\s\-:|]+\|\s*$`, OR (b) at least 4 `- **` type-tagged bullets in Release notes
4. Does NOT match refusal patterns (case-insensitive substring): `"i cannot"`, `"i can't"`, `"i am unable"`, `"as an ai"`, `"i apologize"`, `"죄송하지만"`, `"답변할 수 없"`
5. Does NOT contain `(미기재)` more than 1 time
6. Does NOT contain forbidden journey vocabulary in prose (outside of the "Hardening" bullet): count occurrences of `iter 1` / `iter 2` / `iter 3` / `round 1` / `round 2` — if combined count > 1, fail

Failure of any check → write the response to `.devboard/goals/<goal_id>/report_draft.md` for debug, skip main save, log `NARRATIVE_SKIPPED` decision with `reason=<failed rule>`, return `{status: "skipped"}`.

## Step 4 — Save

Prepend an auto-generated timestamp + warning line, then write:

```
_Auto-generated {utcnow_iso} by agentboard-synthesize-report — manual edits will be overwritten on next run._

{text}
```

Target: `.devboard/goals/<goal_id>/report.md` (UTF-8, overwrite). Use `FileStore.atomic_write` or `Path.write_text`.

## Step 5 — Log decision

```
agentboard_log_decision(
  project_root, task_id, iter=<latest_iter>,
  phase="synthesize_report",
  reasoning="report.md generated ({len} chars, {sec}s)"   # on success
     | "synthesize skipped: <reason>"                     # on skip
  verdict_source="GENERATED" | "SKIPPED",
)
```

## Handoff

- Success: `{status: "generated", path: ".devboard/goals/<goal_id>/report.md"}`
- Skip: `{status: "skipped", reason: "..."}` — caller continues unchanged. Overview tab falls back to legacy `plan_digest` layout; `agentboard export <gid> --source report` exits 1 with a synthesize hint.

## Trigger coverage (reminder)

This skill runs in three contexts — handle each gracefully:

| Caller | Context | What's available |
|---|---|---|
| `agentboard-approval` Step 4.5a | Post-push | All artifacts present; git stats reflect final commit |
| `agentboard-gauntlet` post-lock | Pre-impl | plan.md + challenge.md + brainstorm.md present; decisions.jsonl empty or minimal; git diff vs main may be empty. Skill still emits "What shipped" as "계획 단계 — 구현 진행 중" with truthful provisional framing. |
| Manual | Any | User wants a refresh. Any artifact may be stale; synthesize with what's available. |

Do NOT require all artifacts — fall back gracefully when an input is empty.

## Common bypass attempts — NEVER allow

| User request | Correct reply |
|---|---|
| "그냥 report.md 수동으로 작성해둘게" | 자동 생성 + 덮어쓰기가 기본. 수동 편집은 `agentboard export`로 뽑은 사본에서 한다. 수정된 `report.md`는 다음 실행에서 덮어쓴다. |
| "approval 건너뛰고 여기만 돌려" | 가능 — 이 skill은 manual invocation을 지원. plan-lock된 상태면 된다. |
| "iter 별 이야기도 섞어줘" | 금지 — Release notes 포맷은 의도적으로 journey 정보를 뺀다. iter 기반 서술이 필요하면 Dev tab의 `synthesize-dev-review` / Review tab의 `synthesize-session`을 쓴다. |

## Not your job

- DO NOT modify plan.md / brainstorm.md / challenge.md / decisions.jsonl — read-only.
- DO NOT commit or push — approval's domain.
- DO NOT call external APIs directly — always via Claude Code's Agent tool.
- DO NOT block caller flow — any failure is `NARRATIVE_SKIPPED`.
- DO NOT resurrect `plan_summary.md` — that artifact was retired with `narrative/generator.py`.
