---
name: agentboard-frame
description: D1b SKELETON (2026-04-23). Surfaces hidden assumptions, the riskiest assumption, and checkable success criteria. Reads brainstorm.md YAML frontmatter — NEVER re-decides scope. If a newly surfaced assumption invalidates the chosen scope_mode, routes back to agentboard-intent via AskUserQuestion (never silently overrides). Do NOT invoke until skeleton filled — status=skeleton.
when_to_use: After agentboard-intent completes. Auto-invoked as part of the D1 chain (intent → frame → architecture → stress → lock). Pre-cutover, invoke only when explicitly asked.
---

> **Language**: Respond to the user in Korean. Code, file paths, variable names in English.

> **Status (2026-04-23, SKELETON):** D1b scaffold. Content below is placeholder — Phase steps, prompts, and MCP calls to be filled. See `CLAUDE.md` roadmap + `memory/project_planning_redesign.md`.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

## Role

**Assumption surfacer.** You extract what the user + intent phase did NOT say out loud but must be true for the goal to land. Your output is consumed by architecture (for design decisions) and stress (for adversarial prompts).

You do NOT re-decide scope. If an assumption you surface would invalidate the chosen `scope_mode`, flag it as `new_risk_invalidates_scope: true` and route back to `agentboard-intent` via `AskUserQuestion` — never silently override.

## Input contract

Read `.devboard/goals/<goal_id>/brainstorm.md` YAML frontmatter. Required fields:

- `scope_mode` — carry forward
- `refined_goal` — use as Frame `Problem` root
- `wedge` — carry forward verbatim into `frame.md`
- `req_list` — deferred items seed `non_goals`
- `rationale` — background context

Fallback: if `brainstorm.md` is missing or frontmatter is absent (legacy goal), emit a `no_brainstorm_frontmatter` decision marker and default to parsing the prose body.

## Output contract

Write `.devboard/goals/<goal_id>/gauntlet/frame.md` (directory name kept for backward compat during D transition — to be renamed `phases/` in C-layer work):

```yaml
---
phase: frame
status: completed
inputs:
  - brainstorm.md#<sha256>
problem: <1-2 sentences>
wedge: <from brainstorm>
non_goals:
  - <item>
success_definition:
  - <checkable item>
key_assumptions:
  - <assumption 1>
  - <assumption 2>
riskiest_assumption: <the one most likely to be wrong>
new_risk_invalidates_scope: true | false
---

<prose body — expanded notes, rationale, assumption derivations>
```

## Phases / Steps (TBD)

1. Parse brainstorm.md frontmatter.
2. Surface 2-3 key assumptions (framework / environment / data / user behavior / integration).
3. Identify the single riskiest assumption — the one that, if wrong, would force a restart.
4. Translate `wedge` into checkable success criteria (one testable line per item).
5. Check: do any new assumptions contradict `scope_mode`? If yes, set `new_risk_invalidates_scope: true` + route back to intent via `AskUserQuestion`.
6. Write `frame.md` + log phase completion.

## --deep modes (D2 follow-up)

None planned. Assumption surfacing is singular — depth comes from LLM reasoning quality, not from additional sub-rubrics.

## Handoff

After `frame.md` written:

1. `agentboard_log_decision(phase="frame", verdict_source="COMPLETED")`.
2. If `new_risk_invalidates_scope=true`: emit `AskUserQuestion` (stay | back to intent | amend frame) and pause.
3. Otherwise: invoke `agentboard-architecture` via the Skill tool.

## Required MCP calls (TBD)

| When | Tool |
|---|---|
| Load upstream | (read `brainstorm.md` directly via Read tool; no MCP load helper yet) |
| Write output | (direct file write to `.devboard/goals/<goal_id>/gauntlet/frame.md`) |
| On completion | `agentboard_log_decision(phase="frame", verdict_source="COMPLETED")` |
| On scope-invalidating risk | `AskUserQuestion` + `agentboard_log_decision(phase="frame", verdict_source="SCOPE_REVISIT_REQUESTED")` |

## Freeze notice

Until D3 cutover, NOT auto-invoked. Contract here is what upstream (intent) writes toward and downstream (architecture / stress / lock) reads against.
