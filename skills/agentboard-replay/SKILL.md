---
name: agentboard-replay
description: Time-travel — branch a past run from iteration N with a variant strategy. Invoke when the user says "replay", "try different approach from iteration N", "what if we'd done X instead", "branch from checkpoint", "regression-test this past state", "go back to when X worked", or "explore alternative from iter N". Preserves the original run untouched; new run gets its own run_id and checkpoint trail. LockedPlan is still authoritative (out_of_scope_guard paths still cannot be touched). Useful after agentboard-rca escalates (3 consecutive failures → rethink) to explore a different branch from an earlier checkpoint without losing the failed trail.
when_to_use: User explicitly asks for replay, variant exploration, time-travel, or branching from a past checkpoint. Also proactively suggest after agentboard-rca escalation, or when the user is debating "what if we'd taken approach X" for a completed run.
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

Before any other action, verify agentboard is initialized in this project. Run this Bash command:

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
```

- Output `MISSING` → print this message to the user and **exit the skill immediately** (do NOT call any MCP tools, do NOT proceed with any steps below):
  > agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill.
- Output `OK` → proceed with the skill below.

You are the **Time-travel Replay Agent**. You re-execute runs from past checkpoints with variants.

## Step 1 — Identify source run

Ask user:
- Which run? (call `agentboard_list_runs()` → show id/goal/last_iteration/converged)
- From which iteration? (iter 1, 2, ..., N)
- What variant? ("try async instead", "use different library", free-form annotation)

## Step 2 — Branch

Call MCP tool:
```
agentboard_replay(
  source_run_id="run_abc",
  from_iteration=2,
  variant_note="try async instead of threads"
)
```

Returns:
- `new_run_id` (e.g., "replay_xyz")
- `initial_state` — the graph state at iter N+1, with `converged=False`, `blocked=False`, fresh reflect_json

The new run file at `.agentboard/runs/<new_run_id>.jsonl` starts with a `replay_start` event recording:
- Source run id
- From iteration
- Variant note
- Branched state snapshot (for audit)

## Step 3 — Create task and re-execute

- Create a new Task linked to the original goal (e.g., title: `[replay] <original>`)
- Load the original LockedPlan (unchanged — atomic_steps and out_of_scope_guard still apply)
- Inject the variant note into the next planner call as `previous_strategy`
- Hand off to `agentboard-tdd` at iteration N+1 with:
  - LockedPlan unchanged
  - Fresh convergence/blocked flags
  - `variant_note` as a planning hint

The TDD skill resumes RED-GREEN-REFACTOR from that point with the variant influence.

## Step 4 — Audit

Both runs (original and replay) coexist in `.agentboard/runs/`:
- Original: `run_abc.jsonl`
- Replay: `replay_xyz.jsonl` (starts with `replay_start` event)

Retro reports surface both — variants become material for retrospective pattern analysis.

## Required MCP calls

| When | Tool |
|---|---|
| Discovery | `agentboard_list_runs(project_root)` — show user the candidate runs |
| Branch | `agentboard_replay(project_root, source_run_id, from_iteration, variant_note)` — creates new run_id + initial state |
| New task | `agentboard_start_task(project_root, goal_id, title="[replay] <original>")` — independent task for the variant |
| Resume point | `agentboard_checkpoint(project_root, new_run_id, "replay_resumed", {from_iteration, variant_note})` |

Then hand off to `agentboard-tdd` with the new `{task_id, run_id}` and `variant_note` as the initial `previous_strategy`.

## Discipline

- **Do NOT modify the source run** — replay creates a branch, never overwrites
- **LockedPlan is still authoritative** — even variants can't touch `out_of_scope_guard` paths
- **Variant note is logged** — future retros can see why this path was explored
