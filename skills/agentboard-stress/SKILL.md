---
name: agentboard-stress
description: D1d SKELETON (2026-04-23). Adversarial plan review — finds 4+ failure modes of the PLAN (not the code; that's agentboard-redteam's job after TDD). Each failure mode carries severity + mitigation + replan verdict. Reads prior phase artifacts (brainstorm / frame / arch / design-review). Do NOT invoke until skeleton filled — status=skeleton.
when_to_use: After agentboard-architecture completes (+ agentboard-eng-review if ENG_REVIEW_NEEDED was true). Auto-invoked in the D1 chain. Pre-cutover, invoke only when explicitly asked.
---

> **Language**: Respond to the user in Korean. Code, file paths, variable names in English.

> **Status (2026-04-23, SKELETON):** D1d scaffold. See `CLAUDE.md` roadmap + `memory/project_planning_redesign.md`.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

## Role

**Plan red-team.** Find how the PLAN fails — not the code (that's `agentboard-redteam` after GREEN). You argue against the architecture, question edge-case coverage, probe scope drift vectors, and flag integration gaps.

Distinct from `agentboard-redteam`:
- `stress` runs BEFORE code exists. Target: design decisions.
- `redteam` runs AFTER GREEN. Target: concrete code behavior.

## Input contract

Read `.devboard/goals/<goal_id>/`:
- `brainstorm.md` YAML frontmatter (for scope + chosen alternative context)
- `gauntlet/frame.md` YAML frontmatter (riskiest assumption is a natural attack vector)
- `gauntlet/arch.md` YAML frontmatter (critical_files + edge_cases + test_strategy + `## Design Review` section if `ui_surface=true`)

If `arch.md` contains design-review WARN items, expand on them adversarially.

## Output contract

Write `.devboard/goals/<goal_id>/gauntlet/challenge.md`:

```yaml
---
phase: stress
status: completed
inputs:
  - frame.md#<sha256>
  - arch.md#<sha256>
failure_modes_count: <int, ≥ 4>
critical_count: <int>
high_count: <int>
medium_count: <int>
warrants_replan: true | false   # true if any CRITICAL with "warrants replan"=YES
---

## Failure Mode 1 — {NAME}  ({SEVERITY: CRITICAL | HIGH | MEDIUM})

**Why it fails**: <root cause, tied to arch.md / frame.md evidence>
**Mitigation**: <concrete fix path>
**Warrants replan?**: YES | NO

## Failure Mode 2 — ...

...
```

Minimum: 4 failure modes spanning scope drift / architectural flaws / missing edge cases / integration gaps / test coverage gaps.

## Phases / Steps (TBD)

1. Parse upstream frontmatter + design-review WARN items.
2. Generate 4+ failure modes targeting distinct categories.
3. For each: severity, mitigation, replan verdict.
4. Self-review: any CRITICAL with `Warrants replan?: YES` → set frontmatter `warrants_replan: true`.
5. Write `challenge.md` + log completion.

## --deep modes (D2 follow-up)

- `--deep=codex` → dispatch adversarial review via Codex CLI (`codex challenge` equivalent). Collect Codex's verdict, aggregate with own findings, dedupe on `category_namespace`. For "200 IQ second opinion" on heavy-architecture plans.

## Handoff

After `challenge.md` written:

1. `agentboard_log_decision(phase="stress", verdict_source="COMPLETED", reasoning="<severity counts>")`.
2. If `warrants_replan=true`:
   - `AskUserQuestion`: "CRITICAL 실패 모드가 replan을 요구합니다. (1) architecture 재작성 (2) frame 재작성 (3) 그대로 lock 진행"
   - Routes back to appropriate upstream skill or continues to lock.
3. Otherwise: invoke `agentboard-lock` via the Skill tool.

## Required MCP calls (TBD)

| When | Tool |
|---|---|
| Write output | (direct file write) |
| On completion | `agentboard_log_decision(phase="stress", ...)` |
| On replan request | `AskUserQuestion` → route via Skill tool |

## Freeze notice

Not auto-invoked until D3 cutover. Contract here is what architecture writes toward and lock reads against.
