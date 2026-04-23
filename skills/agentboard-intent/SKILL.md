---
name: agentboard-intent
description: D1a SKELETON (2026-04-23, replacement for agentboard-brainstorm). Discovers what the user wants and commits to a scope decision. Single scope authority — the new chain's gauntlet / stress / lock NEVER re-decide scope. Writes brainstorm.md YAML frontmatter contract (F4 schema) + prose body. Do NOT invoke until skeleton is filled — status=skeleton.
when_to_use: After D3 cutover, for any goal that currently routes to agentboard-brainstorm OR goals with <30 chars / vague language. Pre-cutover, invoke only when explicitly asked ("run intent on X"). Paired with --deep=ceo (10x scope thinking) or --deep=officehours (YC 6 forcing questions).
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

> **Status (2026-04-23, SKELETON):** This skill is part of the D1 phase-skill replacement of the frozen `agentboard-gauntlet` chain. Content below is scaffold-only — phase instructions, prompts, and MCP dispatch to be filled in subsequent iterations. See `CLAUDE.md` "Planning-layer redesign roadmap" + `memory/project_planning_redesign.md`.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

`MISSING` → exit with standard init message. `OK` → proceed.

## Role

**The single scope authority.** You discover what the user wants, surface hidden requests, explore alternatives, and commit to a scope mode + refined goal. Downstream phase skills (frame / architecture / stress / lock) read your output verbatim — they never re-decide scope.

## Input contract

- **User prompt** — the goal text (may be vague, short, or multi-request).
- **`agentboard_relevant_learnings(goal_description)`** — prior session learnings, injected if relevant.
- **Optional `--deep=<mode>`** — depth expansion:
  - `--deep=ceo` → `plan-ceo-review` rubric (10x scope thinking, 4 modes: EXPAND / SELECTIVE / HOLD / REDUCE)
  - `--deep=officehours` → YC 6 forcing questions (demand reality, wedge, observation, etc.)

## Output contract

Write `.devboard/goals/<goal_id>/brainstorm.md` via `agentboard_save_brainstorm` with YAML frontmatter (F4 schema):

```yaml
---
goal_id: <str>
ts: <ISO-8601>
scope_mode: EXPAND | SELECTIVE | HOLD | REDUCE
refined_goal: <1-sentence actionable>
wedge: <narrowest concrete thing>
req_list:
  - {id: R1, text: ..., status: in_scope | deferred}
alternatives_considered:
  - {name: 가장 이상적 | 현실적 | Approach C, summary: ..., chosen: bool}
rationale: <1-2 sentences>
user_confirmed: true | false
---
```

Prose body retains current brainstorm `## Premises / ## Risks / ## Alternatives / ## Existing Code Notes` sections for human readability.

## Phases / Steps (TBD — port from current agentboard-brainstorm)

Current `agentboard-brainstorm` Phase 0–6 structure is the starting point. Port with these changes:

1. **Phase 1 Request Restatement** — keep verbatim; confirm all R-items with user (mandatory).
2. **Phase 2 CLEAR Fast-Path** — keep; single-request + all 3 criteria.
3. **Phase 3 Adaptive Clarification** — keep 3-question cap + NEVER-ASK list.
4. **Phase 4 Alternatives** — keep 이상적 / 현실적 MANDATORY slots + RECOMMENDATION.
5. **Phase 5 Self-review** — keep; log `phase="self_review"` sentinel.
6. **Phase 6 Save + Handoff** — emit full YAML frontmatter per F4 schema; handoff to `agentboard-frame`.

## --deep modes (D2 follow-up)

- `--deep=ceo`: insert `plan-ceo-review` SCOPE EXPANSION / SELECTIVE / HOLD / REDUCE rubric between Phase 3 and Phase 4.
- `--deep=officehours`: replace Phase 3 axes with YC forcing questions (demand reality, status quo, desperate specificity, narrowest wedge, observation, future-fit).

Deep modes are OPT-IN via argument flag. Default (no flag) = lightweight path.

## Handoff

After `agentboard_save_brainstorm` completes successfully:

1. Call `agentboard_log_decision(phase="intent", verdict_source="COMMITTED")` — ready for downstream phase reading.
2. Invoke `agentboard-frame` via the Skill tool.

If user declines ("지금은 아니야" / "나중에"): save only, exit without invoking frame.

## Required MCP calls (TBD — wire up in impl phase)

| When | Tool |
|---|---|
| Phase 0 | `agentboard_list_goals`, `agentboard_add_goal` |
| Phase 0 | `agentboard_relevant_learnings` |
| Phase 5 | `agentboard_log_decision(phase="self_review", verdict_source="PASSED"\|"WARNING")` |
| Phase 6 | `agentboard_save_brainstorm(..., scope_mode, refined_goal, wedge, req_list, alternatives_considered, rationale, user_confirmed)` |
| Handoff | `agentboard_log_decision(phase="intent", verdict_source="COMMITTED")` |

## Freeze notice

Until D3 cutover lands, this skill is NOT auto-invoked. See `memory/feedback_freeze_gauntlet_flow.md`. For now, content here exists only as the contract other D1 skills read against.
