---
name: agentboard-architecture
description: D1c SKELETON (2026-04-23). Locks file structure, test strategy, critical files, out_of_scope_guard, and complexity-based ENG_REVIEW flag. Invokes agentboard-ui-preview (layer 0) + agentboard-design-review when ui_surface=true. Complexity Check emits ENG_REVIEW_NEEDED flag only — NEVER re-decides scope (scope is owned by intent). Do NOT invoke until skeleton filled — status=skeleton.
when_to_use: After agentboard-frame completes. Auto-invoked in the D1 chain. Pre-cutover, invoke only when explicitly asked.
---

> **Language**: Respond to the user in Korean. Code, file paths, variable names in English.

> **Status (2026-04-23, SKELETON):** D1c scaffold. Content below is placeholder. See `CLAUDE.md` roadmap + `memory/project_planning_redesign.md`.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

## Role

**Design lock.** You decide concrete file structure, responsibilities, edge cases, test strategy, and out-of-scope guards. Your output is what `agentboard-stress` adversarially reviews and what `agentboard-lock` atomic-step decomposes.

You do NOT re-decide scope. The Complexity Check (`N>8` files OR `NEW_ABSTRACTIONS≥2`) sets `ENG_REVIEW_NEEDED=true` only — no scope-reduction AskUserQuestion (that was the F4 anti-pattern).

## Input contract

Read `.devboard/goals/<goal_id>/`:
- `brainstorm.md` YAML frontmatter (`scope_mode`, `refined_goal`, `wedge`, `rationale`)
- `gauntlet/frame.md` YAML frontmatter (all fields)

## Output contract

Write `.devboard/goals/<goal_id>/gauntlet/arch.md`:

```yaml
---
phase: architecture
status: completed
inputs:
  - brainstorm.md#<sha256>
  - frame.md#<sha256>
architecture_overview: <2-4 sentences>
data_flow: <input → transform → output>
critical_files:
  - {path: src/..., mode: NEW | MODIFY, purpose: <single-responsibility>}
edge_cases:
  - {case: ..., expected_behavior: ...}
test_strategy:
  must_test: [...]
  do_not_mock: [...]
  safe_to_skip: [...]
critical_path: <the one thing that MUST work>
out_of_scope_guard:
  - <path — intent annotation>
complexity:
  N: <int>
  NEW_COUNT: <int>
  MODIFY_COUNT: <int>
  NEW_ABSTRACTIONS: <int>
  ENG_REVIEW_NEEDED: true | false   # true when N>8 OR NEW_ABSTRACTIONS≥2
ui_surface: true | false
design_review:                        # present only if ui_surface=true
  verdict: APPROVED | WARN | BLOCKER | NOT_APPLICABLE
  mockup_sha: <sha256 of layer-0 ASCII mockup>
---

<prose body: expanded data flow, test rationale, edge case derivations>
```

## Phases / Steps (TBD)

1. Parse upstream frontmatter.
2. Draft architecture overview + data flow.
3. List critical files with Single Responsibility check (split anything containing "and" in `purpose`).
4. Enumerate edge cases.
5. Define test strategy.
6. Declare `out_of_scope_guard`.
7. **Complexity Check** — compute counts, set `ENG_REVIEW_NEEDED`. Do NOT prompt for scope reduction.
8. **UI hook** — if `ui_surface=true`:
   - Invoke `agentboard-ui-preview` with `layer=0` (ASCII mockup + user confirmation + SHA recording).
   - Invoke `agentboard-design-review` (7-pass UI/UX rubric).
   - `BLOCKER` verdict → rewrite arch (1-retry cap with `BLOCKER_OVERRIDDEN` escape hatch).
9. Write `arch.md` + log completion.

## --deep modes (D2 follow-up)

- `--deep=eng` → `plan-eng-review` rubric (architecture coherence, test strategy depth, integration risks). Expand Phase 5 test-strategy block.
- `--deep=design` → `plan-design-review` 0-10 rating per UI dimension (invoked only when `ui_surface=true`; replaces or supplements `agentboard-design-review`).
- `--deep=devex` → `plan-devex-review` persona + magical-moments framing (for developer-facing APIs / CLIs).

## Handoff

After `arch.md` written:

1. `agentboard_log_decision(phase="architecture", verdict_source="COMPLETED", reasoning="<summary>")`.
2. If `ENG_REVIEW_NEEDED=true`:
   - `AskUserQuestion`: "새 파일 {NEW_COUNT}개 / 새 abstraction {NEW_ABSTRACTIONS}개. engineering review를 실행할까요? [Y/n]"
   - Y → invoke `agentboard-eng-review` (it hands off to `agentboard-stress` on completion)
   - n → invoke `agentboard-stress` directly
3. Otherwise: invoke `agentboard-stress` directly.

## Required MCP calls (TBD)

| When | Tool |
|---|---|
| Write output | (direct file write) |
| UI hook | Skill tool → `agentboard-ui-preview` (layer=0), `agentboard-design-review` |
| On completion | `agentboard_log_decision(phase="architecture", ...)` |
| ENG_REVIEW path | `AskUserQuestion`, Skill tool → `agentboard-eng-review` |

## Freeze notice

Not auto-invoked until D3 cutover. Contract here is what frame writes toward and stress / lock read against.
