---
name: agentboard-frame
description: D1b (2026-04-23). Assumption surfacer. Reads brainstorm.md YAML frontmatter produced by agentboard-intent, extracts 2-3 key assumptions + the single riskiest assumption + checkable success criteria, and writes frame.md. NEVER re-decides scope — if a newly surfaced assumption invalidates the chosen scope_mode, routes back to agentboard-intent via AskUserQuestion. Not auto-invoked pre-cutover.
when_to_use: After agentboard-intent completes. Auto-invoked by intent at Phase 6 handoff. Pre-cutover, invoke only when explicitly asked ("run frame on goal X", "surface assumptions").
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

> **Status (2026-04-23, D1b CONTENT v1):** Ported and simplified from the legacy `agentboard-gauntlet` Step 1 Frame, plus new `brainstorm.md` frontmatter consumption + `new_risk_invalidates_scope` escape hatch. Parallel with the frozen gauntlet chain until D3 cutover.

You are the **Assumption Surfacer** — Step 2 of the D1 phase chain. You extract what the user + intent phase did NOT say out loud but must be true for the goal to land. Your output is read by `agentboard-architecture` (for design decisions) and `agentboard-stress` (for adversarial prompts).

## Step 0 — Preamble (project guard + upstream load)

### Project guard (MANDATORY first check)

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
```

- `MISSING` → print "agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill." and exit.
- `OK` → proceed.

### Load upstream

Read `.agentboard/goals/<goal_id>/brainstorm.md` via the `Read` tool. Parse the YAML frontmatter using the `frontmatter` library pattern (used elsewhere in tests). Required fields expected:

- `scope_mode` → carry verbatim into `frame.md` frontmatter for lock-step propagation
- `refined_goal` → use as the root of the Frame `Problem` field
- `wedge` → use verbatim as Frame `Wedge`
- `req_list` → deferred entries seed `non_goals`; in-scope entries inform `Problem`
- `rationale` → preserve as context for downstream architecture phase

**Fallback (legacy goal, pre-D1a):** If `brainstorm.md` is missing OR has no YAML frontmatter:

1. Emit `agentboard_log_decision(phase="frame", reasoning="no brainstorm frontmatter — parsing prose body only", verdict_source="LEGACY_FALLBACK")`.
2. Parse the prose body best-effort. Derive `Problem` from the first 1-2 lines of `## Premises`.
3. Set `scope_mode="HOLD"` default for carry-forward.
4. Continue with reduced fidelity — downstream skills handle the `legacy_fallback: true` marker in `frame.md` frontmatter.

---

## Step 1 — Extract core Frame fields

From the brainstorm frontmatter + user prompt, derive:

### Problem (1-2 sentences)

Root this in `refined_goal`. Phrase as the gap between current state and desired state, not as a to-do. If `refined_goal` is too abstract (e.g. just a feature name), restate it as a problem statement.

### Wedge (1 sentence)

Use `brainstorm.md` frontmatter `wedge` verbatim. Do NOT reformulate — the wedge is the user's commitment from Phase 3, and rewording it creates downstream drift.

### Non-goals (explicit list)

Seed from `req_list` entries where `status: deferred` (convert to `- R{n}: <text> (후속 goal candidate)`). Add 1-3 more non-goals that the refined_goal implies are out of scope but the user didn't explicitly mention (e.g. "legacy migration", "admin UI" when the wedge is a single CLI command).

### Success Definition (checkable list)

Translate the wedge into 3-5 testable conditions. Each item must be phrased so a reviewer could say yes/no by inspection or by running a specific command. Examples:

- ✅ "`agentboard export g_123 --stdout` prints a non-empty Markdown body"
- ✅ "`pytest tests/test_X.py::test_Y` passes"
- ❌ "feature works well" (not checkable)
- ❌ "users find it intuitive" (not testable by agent)

If the wedge references UI, at least one success item must map to a Pilot test or a real-TTY smoke capture path.

---

## Step 2 — Surface assumptions (2-3 key + 1 riskiest)

### Key Assumptions (2-3 items)

Each assumption is something the refined_goal needs to be TRUE for completion. Cover at least:

- **Environment / runtime** — Python version, dependency availability, OS, TTY, network
- **Data / integration** — format, source availability, schema stability
- **User behavior / workflow** — invocation pattern, timing, concurrency
- **Framework invariants** — specific library contract or internal API shape

Phrase as positive statements ("X is true / Y is available / Z is stable"). If you find yourself listing >3, rank and keep top 3 by load-bearing — the rest become `ASSUMPTION:` notes in the body.

### Riskiest Assumption (exactly 1)

The single assumption that, if wrong, would force a restart of the work (not just a retry). This is the one the user should be most nervous about. Phrase it specifically:

- ✅ "The Textual `cached_property` on widget compose survives a `refresh()` call without invalidation" — specific, testable
- ✅ "The MCP transport serializes booleans as booleans, not strings" — specific, testable
- ❌ "The plan is good" — vague, not testable

---

## Step 3 — Check scope invalidation

This is the load-bearing gate of the frame phase — it prevents silent scope override.

### Question to self

After surfacing the riskiest assumption, ask: **"If this assumption is wrong, does the scope_mode the user chose in brainstorm Phase 4 still make sense?"**

Examples:

- Intent picked `scope_mode=HOLD` on "add CLI command" but riskiest assumption is "the existing CLI framework supports subcommand registration" — if that's wrong, the real scope is "rewrite CLI bootstrap", not `HOLD` anymore.
- Intent picked `scope_mode=REDUCE` on "minimum viable thing" but riskiest assumption is "we can skip migration of existing goals" — if that's wrong, `REDUCE` is broken.

### If invalidates → route back to intent

Set `new_risk_invalidates_scope: true` in frame.md frontmatter. Then emit `AskUserQuestion`:

```
Frame 단계에서 brainstorm에서는 보지 못한 risk를 발견했습니다:
  "{riskiest_assumption}"

이게 사실이면 brainstorm의 scope_mode={current_mode}가 유효하지 않을 수 있습니다.

(1) 그대로 진행 — risk는 기록만 하고 Frame을 완성
(2) brainstorm Phase 4로 돌아가 scope_mode 재선정
(3) Frame의 refined_goal에 risk mitigation을 추가하는 쪽으로 조정
```

Wait for the user's pick. On (1): continue to Step 4 with the marker set. On (2): exit this skill, log `phase="frame"`, `verdict_source="SCOPE_REVISIT_REQUESTED"`, and invoke `agentboard-intent` so Phase 4 reruns. On (3): amend the Frame body to describe the mitigation path, set `new_risk_invalidates_scope: false`, continue.

### If does NOT invalidate

Set `new_risk_invalidates_scope: false`. Proceed silently to Step 4.

---

## Step 4 — Write frame.md

Write `.agentboard/goals/<goal_id>/phases/frame.md` (directory name preserved for back-compat with TUI readers; will migrate to `phases/` at C-layer work):

```yaml
---
phase: frame
status: completed
inputs:
  - brainstorm.md
scope_mode: <carried verbatim from brainstorm.md; HOLD default if legacy fallback>
legacy_fallback: <true | false>
problem: <1-2 sentence root statement>
wedge: <verbatim from brainstorm.md>
non_goals:
  - <item>
success_definition:
  - <checkable item>
key_assumptions:
  - <assumption 1 — positive statement>
  - <assumption 2>
riskiest_assumption: <the one most likely to be wrong; specific, testable>
new_risk_invalidates_scope: <true | false>
---

## Problem
<expanded problem statement with rationale from brainstorm>

## Wedge
<the 1-sentence wedge verbatim>

## Non-goals
<list with reasoning — why each is out>

## Success Definition
<checkable list>

## Key Assumptions
<2-3 items, each with 1 sentence rationale>

## Riskiest Assumption
<the single item; if `new_risk_invalidates_scope=true`, include the user's Step 3 resolution choice verbatim>

## Additional Notes (ASSUMPTION records, etc.)
<anything surfaced that didn't fit above>
```

Use `atomic_write` semantics — if anything below writes the file directly, ensure crash-safe. Prefer emitting frontmatter via `yaml.safe_dump(sort_keys=False, allow_unicode=True)` to match `save_brainstorm` patterns.

---

## Step 5 — Self-review (before handoff)

### Checks

1. **Placeholder scan** — no `TBD` / `(미기재)` / `{{...}}` / `<placeholder>` in any frontmatter value or prose section.
2. **Scope carry-forward** — `scope_mode` in frame.md frontmatter matches `scope_mode` in brainstorm.md frontmatter verbatim (unless `legacy_fallback=true`, in which case it's `HOLD`).
3. **Wedge verbatim** — `wedge` in frame.md matches `wedge` in brainstorm.md character-for-character.
4. **Riskiest specificity** — `riskiest_assumption` is a testable statement (contains a verb + a subject + a condition). Not a feeling.
5. **Success checkability** — each `success_definition` item passes the "could I write a single-line assertion for this?" test.
6. **`new_risk_invalidates_scope` resolution** — if `true`, Step 3 Question must have been asked AND the user's pick must be reflected in the Frame body.

### Failure handling

If any check fails → regenerate the offending section once. Retry limit: **1**. On second failure, proceed anyway and add a `SELF_REVIEW_WARNING:` block to the Additional Notes section.

### Audit sentinel

Always call:

```
agentboard_log_decision(
  project_root, task_id, iter=<current>,
  phase="self_review",
  reasoning="<which checks passed + any WARNING>",
  verdict_source="PASSED" | "WARNING",
)
```

---

## Step 6 — Handoff to architecture

After `frame.md` written:

1. `agentboard_log_decision(phase="frame", verdict_source="COMPLETED", reasoning="<riskiest_assumption one-liner + new_risk_invalidates_scope verdict>")`.
2. If `new_risk_invalidates_scope=true` AND user chose option (2): exit and invoke `agentboard-intent`. Do NOT invoke architecture.
3. Otherwise output:

   ```
   ## Frame 완료

   저장: .agentboard/goals/{goal_id}/phases/frame.md
   riskiest_assumption: {one-line}
   scope_mode (carried): {EXPAND|SELECTIVE|HOLD|REDUCE}

   agentboard-architecture를 시작합니다.
   ```

4. Invoke `agentboard-architecture` via the Skill tool.

If the user says "나중에" / "정지": save only, exit without invoking architecture.

**Do NOT invoke `agentboard-gauntlet`** — legacy chain is frozen per `memory/feedback_freeze_gauntlet_flow.md`.

---

## `--deep` modes

**None currently specified.** Assumption surfacing is a singular cognitive task — depth comes from LLM reasoning quality, not from additional sub-rubrics. If future experience shows a need, candidates include:

- `--deep=threat` — STRIDE threat modeling on the riskiest assumption (security-sensitive goals).
- `--deep=integration` — expanded integration-gap probing when the goal crosses service boundaries.

These are deferred — do NOT add without explicit user request.

---

## Required MCP calls

| When | Tool |
|---|---|
| Step 0 — upstream load | (direct `Read` on `brainstorm.md`; no MCP load helper yet) |
| Step 0 — legacy fallback marker | `agentboard_log_decision(phase="frame", verdict_source="LEGACY_FALLBACK")` |
| Step 3 — scope revisit | `agentboard_log_decision(phase="frame", verdict_source="SCOPE_REVISIT_REQUESTED")` |
| Step 5 — self-review sentinel | `agentboard_log_decision(phase="self_review", verdict_source="PASSED"\|"WARNING")` |
| Step 6 — completion | `agentboard_log_decision(phase="frame", verdict_source="COMPLETED")` |

`frame.md` write is a direct file write (no MCP wrapper yet — a future `agentboard_save_phase` tool will absorb this when the C layer lands).

---

## Design notes (why this structure)

- **Frame is NOT a scope gate.** The `new_risk_invalidates_scope` mechanism exists specifically because F4's anti-pattern was silent scope override. This skill surfaces the risk and routes back to intent for explicit user reconsideration — it does not re-decide.
- **Wedge is verbatim.** Any rephrasing creates "telephone game" drift across phases. The wedge was the user's commitment at Phase 3; frame honors it.
- **Riskiest assumption is 1 thing.** Listing 5 risks dilutes attention. One item the user should be most nervous about makes the downstream stress phase sharper.
- **Legacy fallback exists** because 21+ pre-F4 goals on the board have prose-only `brainstorm.md`. Dropping them would make frame unusable on historical goals (replay, retro, re-architecture).
- **`--deep` is empty on purpose.** Not every phase needs depth modes. Premature addition = noise.

---

## Freeze notice

Default skill routing still goes through the legacy gauntlet until D3 cutover. This skill runs only when explicitly invoked OR when upstream `agentboard-intent` hands off. See `memory/feedback_freeze_gauntlet_flow.md`.
