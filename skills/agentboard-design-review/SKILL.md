---
name: agentboard-design-review
description: |
  UI/UX design-judgment gate for ui_surface tasks. Runs after gauntlet writes
  arch.md (and ui-preview Layer 0 if applicable) and before Challenge, scoring
  the plan against a 7-pass rubric (Information Architecture, Interaction
  State Coverage, User Journey, AI Slop Risk, Design System Alignment,
  Responsive+Keyboard, Unresolved Decisions). Verdict (APPROVED / WARN /
  BLOCKER) is upserted into arch.md's ## Design Review section and logged
  via agentboard_log_decision with phase="design_review". Skip entirely when
  ui_surface=False or the deliverable is not a mountable UI.
when_to_use: |
  Invoked automatically by agentboard-gauntlet after Layer 0 mockup confirmation.
  Not meant for direct user invocation.
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

Before any other action, verify agentboard is initialized in this project:

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
```

- Output `MISSING` → print init hint and exit.
- Output `OK` → proceed.

You are the **Design Judge** — an agentboard-style port of gstack's
`plan-design-review`. Your job: run a 7-pass UI/UX rubric over the locked-in
architecture BEFORE any code is written, surface fixable UX debt while it is
still cheap, and block the plan when interaction-level defects (modal stacking,
focus trap absence, missing empty/error states, z-order conflicts) would ship
otherwise.

## Phase 0 — Gate (decide whether design-review even applies)

Before running any pass, answer two questions:

1. **Is `task.metadata.ui_surface` True?** — read the active task's metadata
   via the loaded context (the gauntlet sets this flag). If False, exit
   immediately with `verdict_source="NOT_APPLICABLE"`.
2. **Is the deliverable a mountable UI?** — even when `ui_surface=True`
   triggers by keyword heuristic, the goal may be a meta-artifact (e.g. a
   SKILL.md prompt file *about* UI review, a doc-only change, a migration
   that happens to mention "ui" in text). Look at the locked plan's
   `atomic_steps[*].impl_file`:
   - If every impl_file is `.md`, `.txt`, `.yaml`, or similar doc/config
     → NOT_APPLICABLE.
   - If any impl_file is Python/TS/etc. rendering UI (Textual widget,
     React component, HTML template) → applicable, continue.

On NOT_APPLICABLE: skip Phases 1-4, go straight to Phase 5 Log & Handoff
with `verdict_source="NOT_APPLICABLE"` and a one-line reason. The gauntlet
will proceed as if design-review did not run.

## Phase 1 — Context Harvest

Read the inputs that exist (skip silently if a file is missing):
- `.agentboard/goals/<goal_id>/phases/arch.md` — required
- `.agentboard/goals/<goal_id>/brainstorm.md` — helpful for user journey
- `.agentboard/goals/<goal_id>/gauntlet/arch_mockup.md` or the Layer 0
  block inside arch.md — text mockup of intended layout

## Phase 2 — Seven Rubric Passes

For each pass, rate the plan 0-10 with a one-line justification.

### Pass 1 — Information Architecture
What does the user see first, second, third? Is the visual hierarchy spelled
out in arch.md? If the plan only says "show X" without ranking X vs Y vs Z,
rate low.

### Pass 2 — Interaction State Coverage
Does the plan name the loading / empty / error / success / partial states?
When the plan mentions a modal, overlay, drawer, or popover, does arch.md
also specify: focus trap behavior, ESC / outside-click dismiss order, and
the background's pointer/key blocking while the overlay is open? If any of
these is absent for a named overlay, call it out as a concrete fix
(e.g. "Pass 2: z-order missing for the split-pane command when a modal is
open — add explicit dismiss-modal-first rule").

### Pass 3 — User Journey & Emotional Arc
Does the plan trace a realistic user path from entry → action → outcome?
Empathy-as-simulation: can you narrate what the user feels at each step?

### Pass 4 — AI Slop Risk
Does the plan describe specific, intentional UI — or generic patterns
(3-column grid, stock-hero, infinite scroll feed, "settings page")?
Generic = low score.

### Pass 5 — Design System Alignment
Does the plan reuse an existing DESIGN.md / token palette / component
library, or invent parallel primitives?

### Pass 6 — Responsive + Keyboard / TUI Focus Chain
Mobile breakpoints, keyboard navigation order, screen-reader labels.
For TUI, the Textual focus chain and pilot-reachable key bindings.

### Pass 7 — Unresolved Design Decisions
What must the user decide before code is written that the plan has
left implicit?

## Phase 3 — Verdict

Aggregate the 7 pass scores (each 0-10) into one verdict:

| All pass scores | Verdict | Next step |
|---|---|---|
| every pass ≥7 | **APPROVED** | proceed to gauntlet Step 4 Challenge |
| any pass 5 or 6 (none below 5) | **WARN** | upsert fix proposals into arch.md, wait for user ack, then proceed |
| any pass <5 | **BLOCKER** | return control to gauntlet Step 3 (Arch) with the failing pass(es) named |

Use 0-10 scoring consistently — never emit a half-point, never emit
"N/A" for a required pass (skip only if the entire skill exited via
Phase 0 NOT_APPLICABLE). A single <5 trumps every ≥7.

### BLOCKER retry cap and override escape hatch

A BLOCKER verdict returns control to gauntlet Step 3 (Arch) for rewrite
**at most one retry** — i.e. the Arch rewrite → design-review loop is
allowed to fire once. On the second BLOCKER in the same goal, you MUST
stop the loop and surface the escape hatch via `AskUserQuestion`:

```
Options:
  A) Rewrite arch once more (last manual try)
  B) Override this BLOCKER and proceed to Challenge
  C) Abandon this goal
```

- A → user manually rewrites; re-run design-review ONCE more, then enforce
  the same stop rule if it still BLOCKs.
- B → log `verdict_source="BLOCKER_OVERRIDDEN"` to decisions.jsonl and
  continue to Challenge. The override is a recorded decision, not a bypass.
- C → mark the goal as blocked, exit the skill.

Why: SKILL.md contracts are advisory markdown, so an infinite "BLOCK →
rewrite → BLOCK" loop is a real risk if Claude fixates on a pass score.
The retry 1 + override + sentinel pattern is the same one used by
`agentboard-brainstorm` Phase 5 self-review.

## Phase 4 — Upsert into arch.md (idempotent)

Write the verdict + per-pass scores + fix proposals to
`.agentboard/goals/<goal_id>/phases/arch.md` under a dedicated
`## Design Review` section. Upsert rule: **idempotent replace, not append** —
if a prior `## Design Review` heading is already present in arch.md, locate
its block (from that heading up to the next top-level `##` heading or EOF)
and REPLACE it wholesale. Do not stack multiple blocks. A second design-review
run on the same goal must leave arch.md with exactly one `## Design Review`
section.

### Body format — `| Pass | Before | After | Fix |` table (MANDATORY)

The body of `## Design Review` MUST be a markdown table with EXACTLY these
four columns, in this order. Do NOT use a bullet list, a prose paragraph,
or a score tuple — those formats make the before/after diff invisible to
reviewers. The separator row (`| --- | --- | --- | --- |`) is also
mandatory so the document renders as a real table.

```markdown
## Design Review
- Verdict: APPROVED | WARN | BLOCKER | BLOCKER_OVERRIDDEN
- Reviewed: <utc_iso>

| Pass | Before | After | Fix |
| --- | --- | --- | --- |
| Information Architecture | n/a | 8 | — |
| Interaction State Coverage | n/a | 5 | add z-order + focus-trap for modal M |
| User Journey | n/a | 7 | — |
| AI Slop Risk | n/a | 9 | — |
| Design System Alignment | n/a | 8 | — |
| Responsive + Keyboard | n/a | 6 | document mobile breakpoint for pane split |
| Unresolved Decisions | n/a | 7 | — |
```

Column semantics:
- **Pass** — the exact 7-pass name, in the order listed above.
- **Before** — the After score from the previous design-review run on
  this same goal. On the first run, use the literal string `n/a`.
- **After** — the score this run just produced (integer 0-10, or the
  literal `PASS`/`FAIL` only if Phase 0 produced NOT_APPLICABLE — in
  which case the whole table may be replaced with the single line
  `Skipped — reason: <…>`).
- **Fix** — a one-line fix proposal if After < 7, else the em-dash `—`.
  Fix cells are what Challenge will read, so make them actionable.

### Re-run: promote prior After into Before (carry over)

On a re-review of the same goal (i.e. when arch.md already contains a
`## Design Review` block), you MUST carry over each row's prior After
value into the new row's Before column before writing the new After.
Algorithm:

1. Read arch.md; if no `## Design Review` heading → first run, every
   Before = `n/a`. Skip to step 4.
2. Parse the existing table: for every row whose first cell matches a
   known Pass name, capture column 3 (After) as `prior_after[name]`.
3. When emitting the new table, set `Before = prior_after.get(name, "n/a")`.
   A best-effort match is fine — if the prior table was hand-edited and
   the parse fails, fall back to `n/a` and continue. Do NOT raise.
4. Write the new `## Design Review` block, replacing (not appending) the
   prior one per the idempotent rule above.

This means a reviewer can glance at arch.md and see exactly which pass
scores moved during the rewrite, without opening decisions.jsonl.

## Phase 5 — Log & Handoff (MANDATORY — sentinel before return)

Before returning control to the gauntlet, you MUST log a single
decisions.jsonl entry via `agentboard_log_decision`. Without this sentinel,
retros cannot grep for whether design-review ran at all.

```
agentboard_log_decision(
  project_root=<abs path>,
  task_id=<task_id>,
  iter=<current_iter>,
  phase="design_review",
  reasoning="<one-line: min pass + its score + worst finding>",
  verdict_source=<"APPROVED" | "WARN" | "BLOCKER" | "BLOCKER_OVERRIDDEN" | "NOT_APPLICABLE">,
)
```

Then hand off according to the verdict:

| verdict_source | Next step |
|---|---|
| APPROVED | return to agentboard-gauntlet; proceed to Step 4 (Challenge) |
| WARN | return to agentboard-gauntlet with fix proposals upserted into arch.md; Challenge reads the amended arch |
| BLOCKER | return to agentboard-gauntlet Step 3 (Arch) for rewrite — see retry-1 + override rule above |
| BLOCKER_OVERRIDDEN | same as APPROVED — proceed to Challenge with the override recorded |
| NOT_APPLICABLE | return immediately; gauntlet proceeds as if design-review did not run |


