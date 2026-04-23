---
name: agentboard-architecture
description: D1c (2026-04-23). Design lock. Reads brainstorm.md + frame.md YAML frontmatter, decides concrete file structure (Single Responsibility enforced), test strategy, critical path, out_of_scope_guard, and emits an ENG_REVIEW_NEEDED flag on complexity. Invokes ui-preview layer=0 + design-review 7-pass when ui_surface=true. NEVER re-decides scope (owned by intent) — Complexity Check sets a flag only, never prompts for scope reduction (that was the F4 anti-pattern). Not auto-invoked pre-cutover.
when_to_use: After agentboard-frame completes. Auto-invoked by frame at Step 6 handoff. Pre-cutover, invoke only when explicitly asked.
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

> **Status (2026-04-23, D1c CONTENT v1):** Ported from the legacy `agentboard-gauntlet` Step 3 Architecture + Complexity Check (with F4 Case 2 scope-reduction removed), plus frame.md frontmatter consumption, UI hook integration, and `--deep=eng` / `--deep=design` / `--deep=devex` spec. Parallel with the frozen gauntlet chain until D3 cutover.

You are the **Design Lock** — Step 3 of the D1 phase chain. You translate the user's committed scope (from intent) and the surfaced assumptions (from frame) into concrete file-level design decisions. Your output is what `agentboard-stress` adversarially reviews and what `agentboard-lock` atomic-step decomposes.

## Step 0 — Preamble (project guard + upstream load)

### Project guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

### Load upstream

Read via the `Read` tool and parse YAML frontmatter:

- `.devboard/goals/<goal_id>/brainstorm.md` — `scope_mode`, `refined_goal`, `wedge`, `rationale`, `alternatives_considered` (chosen entry)
- `.devboard/goals/<goal_id>/gauntlet/frame.md` — `problem`, `wedge`, `non_goals`, `success_definition`, `key_assumptions`, `riskiest_assumption`, `new_risk_invalidates_scope`

If `frame.md.new_risk_invalidates_scope=true` AND the user's resolution pick at frame Step 3 was "continue" (option 1): carry the riskiest assumption into the architecture's `test_strategy.must_test` so downstream Challenge has adversarial material to work with.

---

## Step 1 — Architecture Overview (2-4 sentences)

State the technical approach in plain language. Reference the chosen alternative from `brainstorm.alternatives_considered`. Examples:

- ✅ "Extend `save_brainstorm` with optional structured kwargs + YAML frontmatter emission via `yaml.safe_dump`. MCP tool schema adds 7 fields. Gauntlet SKILL.md reads the frontmatter. No LockedPlan schema change." (F4 example)
- ❌ "Build the feature in the backend" (no content)

This paragraph is what downstream `agentboard-stress` will try to poke holes in.

---

## Step 2 — Data Flow (input → transform → output)

One arrow per flow. Examples:

```
User prompt
  ↓
agentboard-intent (Phase 1-6)
  ↓ save_brainstorm(scope_mode, refined_goal, ...)
brainstorm.md (YAML frontmatter + prose body)
  ↓
agentboard-frame (read frontmatter + surface assumptions)
  ↓
frame.md (YAML frontmatter + prose body)
  ↓
agentboard-architecture ← YOU ARE HERE
  ↓ write arch.md
```

Cover the happy path + at least one error branch (what happens when an input is missing / malformed).

---

## Step 3 — Critical Files (with Single Responsibility enforcement)

List every file you'll create or modify. Tag each with `[NEW]` or `[MODIFY]` and a single-responsibility purpose statement.

### Format

```yaml
critical_files:
  - path: src/agentboard/X.py
    mode: NEW
    purpose: <one single-responsibility sentence — no "and">
  - path: src/agentboard/Y.py
    mode: MODIFY
    purpose: <what changes>
  - path: tests/test_X.py
    mode: NEW
    purpose: <what it tests>
```

### Single Responsibility rule (MANDATORY)

If a `purpose` sentence contains "and", "with", or references multiple concerns — **split the file**. Examples:

- ❌ Bad: `src/auth.py [MODIFY]: handles login, session management, and token refresh`
- ✅ Good:
  - `src/auth_login.py [NEW]: login flow`
  - `src/auth_session.py [NEW]: session state transitions`
  - `src/auth_token.py [NEW]: token refresh`

### Exceptions

One responsibility can legitimately span multiple observable behaviors if they share state. E.g. a `Counter` class with `increment`, `reset`, `read` is one responsibility. Use judgment; when in doubt, split.

---

## Step 4 — Edge Cases

List every edge case with its expected behavior. Cover at least:

- **Empty / None input** — what happens when a consumer passes `""`, `None`, `[]`, `{}`
- **Invalid input type** — wrong shape, wrong type (especially if the function accepts `dict` or `list` and receives string)
- **Boundary values** — zero, empty collection, max size
- **Missing upstream** — what if the file this skill needs doesn't exist
- **Concurrent access** — if the skill writes shared state

### Format

```yaml
edge_cases:
  - case: save_brainstorm called with alternatives_considered=['not a dict']
    expected: raises ValueError with index + type (not AttributeError)
  - case: brainstorm.md missing frontmatter (legacy goal)
    expected: downstream defaults scope_decision=HOLD + logs LEGACY_FALLBACK
```

The `riskiest_assumption` from frame.md MUST appear in at least one edge_case as a probe — "if {assumption} is wrong, what's the failure mode?"

---

## Step 5 — Test Strategy

Partition into three buckets:

- **must_test** — behaviors where a test failure would block the goal. Drawn from `frame.success_definition` + `edge_cases` + the riskiest assumption probe.
- **do_not_mock** — real filesystem, real MCP dispatch, real process boundaries. Following the "integration tests must hit real surfaces" pattern from memory.
- **safe_to_skip** — type coercion edge cases in MVP, localization on solo-dev goals, performance under load when the goal doesn't scale yet.

### Format

```yaml
test_strategy:
  must_test:
    - <behavior 1, 1 line>
    - <behavior 2>
  do_not_mock:
    - <surface 1 — why real>
  safe_to_skip:
    - <skipped case + rationale>
```

---

## Step 6 — Critical Path

One sentence: **the one thing that MUST work for everything else to work**. This is what `agentboard-stress` will attack hardest and what `agentboard-lock` will order first in `atomic_steps`.

Example:
- F4 critical path: "save_brainstorm emits parseable YAML frontmatter" — everything downstream (gauntlet frontmatter read, scope_decision injection) depends on it.

If you can't name one, the design is under-specified — go back to Step 1.

---

## Step 7 — Out-of-scope Guard

Exact paths/modules the implementation must NOT touch. Optionally annotate each with intent:

```yaml
out_of_scope_guard:
  - src/agentboard/gauntlet/lock.py — keep; build_locked_plan still used
  - src/agentboard/models.py — LockedPlan schema untouched
  - src/agentboard/tui/ — not this phase's work
```

`brainstorm.req_list` entries with `status=deferred` should be reflected here as path-level guards where relevant.

These paths become the `out_of_scope_guard` field in the locked plan — `agentboard-tdd` (or its D1f successor) hard-blocks writes to them.

---

## Step 8 — Complexity Check (ENG_REVIEW_NEEDED flag ONLY)

**F4 anti-pattern reminder:** Prior version had a "Case 2: scope creep" `AskUserQuestion` that asked the user to cut scope mid-architecture. That was the silent scope-override hazard. **REMOVED.** This step sets a flag only.

### Counts

```
N = total file count
NEW_COUNT = files with mode: NEW
MODIFY_COUNT = files with mode: MODIFY
NEW_ABSTRACTIONS = new classes / services / modules
```

### Trigger

`N > 8` OR `NEW_ABSTRACTIONS ≥ 2`

### Branches (2 cases only)

- **Case 1: No trigger** → output `✅ Complexity OK: {N} files ({NEW_COUNT} new, {MODIFY_COUNT} modified, {NEW_ABSTRACTIONS} new abstractions).` Set `ENG_REVIEW_NEEDED=false`.
- **Case 2: Trigger fired** → output `⚠️ {N} files ({NEW_COUNT} new, {MODIFY_COUNT} modified, {NEW_ABSTRACTIONS} new abstractions). Engineering review recommended.` Set `ENG_REVIEW_NEEDED=true`. Proceed to Step 9 — do NOT prompt for scope reduction (scope is owned by intent; if the user wants to reduce, they return to intent).

---

## Step 9 — UI hook (when `ui_surface=true`)

Detect `ui_surface` by keyword scan of the architecture body + critical_files paths. Case-insensitive matches on: `tui`, `textual`, `widget`, `pilot`, `browser`, `ui`, `frontend`. Exclude out_of_scope_guard entries from the scan (F4 taught us that keyword appearance in a NOT-touch list is a false positive).

### `ui_surface=false`

Skip this step. Go to Step 10.

### `ui_surface=true`

Invoke `agentboard-ui-preview` via the `Skill` tool with `layer=0`:

```
Skill(agentboard-ui-preview, "layer=0 goal_id=<goal_id>")
```

That skill produces a Layer 0 ASCII mockup, asks the user to confirm, and records the confirmed mockup SHA back into `arch.md` under a `## Screenshots / Diagrams` section. The gauntlet hash will cover the visual intent.

After Layer 0 confirmed, invoke `agentboard-design-review` via the `Skill` tool:

```
Skill(agentboard-design-review, "goal_id=<goal_id>")
```

design-review scores the arch + mockup against a 7-pass UI/UX rubric (Information Architecture, Interaction State Coverage, User Journey, AI Slop Risk, Design System Alignment, Responsive+Keyboard, Unresolved Decisions). Branches:

- **APPROVED** or **WARN** → continue to Step 10. WARN means fix proposals were upserted into arch.md's `## Design Review` section — `agentboard-stress` reads them.
- **BLOCKER** → return to Step 1 (Architecture Overview) for rewrite. 1-retry cap with `BLOCKER_OVERRIDDEN` escape hatch if the user insists.
- **NOT_APPLICABLE** → deliverable is not a mountable UI (e.g. a meta-goal whose impl is a markdown skill file). Continue.

---

## Step 10 — Write arch.md

Write `.devboard/goals/<goal_id>/gauntlet/arch.md`:

```yaml
---
phase: architecture
status: completed
inputs:
  - brainstorm.md
  - frame.md
scope_mode: <carried verbatim from brainstorm/frame>
architecture_overview: <2-4 sentences>
critical_files:
  - {path: ..., mode: NEW|MODIFY, purpose: ...}
edge_cases:
  - {case: ..., expected_behavior: ...}
test_strategy:
  must_test: [...]
  do_not_mock: [...]
  safe_to_skip: [...]
critical_path: <one-sentence>
out_of_scope_guard:
  - <path — intent annotation>
complexity:
  N: <int>
  NEW_COUNT: <int>
  MODIFY_COUNT: <int>
  NEW_ABSTRACTIONS: <int>
  ENG_REVIEW_NEEDED: <bool>
ui_surface: <bool>
design_review:                # present only if ui_surface=true
  verdict: APPROVED | WARN | BLOCKER | NOT_APPLICABLE
  mockup_sha: <sha256 or null>
---

## Architecture Overview
<2-4 sentences>

## Data Flow
<input → transform → output diagram>

## Critical Files
<table or list with purpose>

## Edge Cases
<each with expected behavior>

## Test Strategy
### Must test
- ...
### Do not mock
- ...
### Safe to skip
- ...

## Critical Path
<one sentence>

## Out-of-scope Guard
<list>

## Complexity Check
<Case 1 or Case 2 output line>

## Screenshots / Diagrams  (only if ui_surface=true)
<mockup reference + design-review verdict block>

## Design Review  (only if ui_surface=true)
<upserted by agentboard-design-review skill>
```

---

## Step 11 — Self-review + audit sentinel

### Checks

1. **Single Responsibility** — re-scan every `purpose` for "and" / "with"; any violation = split.
2. **Critical path is testable** — one sentence, verb + subject + measurable outcome.
3. **Edge cases include riskiest assumption** — frame's `riskiest_assumption` appears as a probe case.
4. **Out-of-scope guard is non-empty** — at least the standard invariants (`models.py`, `iron_law.py`, other phases' files).
5. **Complexity counts correct** — N = len(critical_files), NEW_COUNT + MODIFY_COUNT = N.
6. **ENG_REVIEW_NEEDED derivation correct** — matches Step 8 trigger.
7. **`ui_surface` false positives** — if `tui` / `ui` keyword appears ONLY in out_of_scope_guard, set `ui_surface=false` (F4 lesson).

### Audit log

```
agentboard_log_decision(
  phase="self_review",
  reasoning="<checks passed + any WARNING>",
  verdict_source="PASSED" | "WARNING",
)
```

---

## Step 12 — Handoff to stress

After `arch.md` written:

1. `agentboard_log_decision(phase="architecture", verdict_source="COMPLETED", reasoning="<critical_path one-liner + ENG_REVIEW_NEEDED verdict>")`.
2. Branch on `ENG_REVIEW_NEEDED`:
   - **false** → invoke `agentboard-stress` via the `Skill` tool directly.
   - **true** → `AskUserQuestion`: "이 계획은 {NEW_COUNT}개의 새 파일 + {NEW_ABSTRACTIONS}개 새 abstraction을 포함합니다. stress 진입 전 agentboard-eng-review를 실행할까요? (권장) [Y/n]"
     - `Y` → invoke `agentboard-eng-review` via `Skill`. After eng-review completes, it invokes `agentboard-stress` itself.
     - `n` → invoke `agentboard-stress` directly. Note: user declined ENG_REVIEW despite the flag; log `verdict_source="ENG_REVIEW_DECLINED"`.
3. If `ui_surface=true` AND `design_review.verdict=BLOCKER` AND user did not override: do NOT invoke stress. Return to Step 1 for rewrite.

**Do NOT invoke `agentboard-gauntlet`** — legacy chain frozen per `memory/feedback_freeze_gauntlet_flow.md`.

---

## `--deep` modes

### `--deep=eng` — plan-eng-review rubric

Expand Step 5 Test Strategy with the `gstack plan-eng-review` depth:

- **Architecture coherence** — does the critical_files list actually deliver the refined_goal? Draw a mental execution trace.
- **Test coverage gaps** — for each `must_test` entry, which component / interaction does it leave uncovered?
- **Integration risks** — where does this change touch modules outside critical_files? Are side-effects accounted for?
- **Performance footprint** — any N² loops, unbounded reads, blocking calls on the hot path?
- **Diagrams** — if data flow is non-trivial, include ASCII sequence/state diagram inline.

Invocation: `/agentboard-architecture --deep=eng` or user writes "eng review this design".

### `--deep=design` — plan-design-review rubric (ui_surface=true only)

Replace or supplement `agentboard-design-review` with 0-10 scores per UI dimension:

- Information Architecture (0-10)
- Interaction State Coverage (0-10)
- User Journey (0-10)
- AI Slop Risk (0-10)
- Design System Alignment (0-10)
- Responsive / Keyboard (0-10)
- Unresolved Decisions (0-10)

Output: what each dimension would need to score 10, and which are the weakest. Fix proposals are upserted into arch.md's `## Design Review` section.

Invocation: `/agentboard-architecture --deep=design`. Only meaningful when `ui_surface=true`; otherwise no-op + log `verdict_source="DEEP_DESIGN_NOT_APPLICABLE"`.

### `--deep=devex` — plan-devex-review rubric (developer-facing APIs / CLIs)

When the critical path affects a developer-facing surface (CLI, SDK, public API, MCP tool schema), expand with:

- **Persona** — who's the builder using this? Not the end user.
- **Magical moments** — the 1-2 steps in the workflow that make the tool feel good.
- **Friction audit** — unnecessary steps, confusing names, unhelpful errors.
- **Benchmark** — how does this compare to the closest competitor on the same dimension?

Invocation: `/agentboard-architecture --deep=devex`. Use for agentboard skill file designs, MCP tool additions, CLI subcommands.

### Invariants across `--deep` modes

- Steps 1-8 and 10-12 unchanged.
- Complexity Check still runs and sets `ENG_REVIEW_NEEDED` normally.
- `ui_surface` detection unchanged.
- Self-review (Step 11) unchanged.

---

## Required MCP calls

| When | Tool |
|---|---|
| Step 0 — upstream load | (direct `Read` on brainstorm.md + frame.md) |
| Step 9 — UI preview (ui_surface=true) | `Skill(agentboard-ui-preview, "layer=0 ...")` |
| Step 9 — design review (ui_surface=true) | `Skill(agentboard-design-review, "...")` |
| Step 11 — self-review sentinel | `agentboard_log_decision(phase="self_review", ...)` |
| Step 12 — completion | `agentboard_log_decision(phase="architecture", ...)` |
| Step 12 — eng-review branch | `Skill(agentboard-eng-review, "...")` or `Skill(agentboard-stress, "...")` |

`arch.md` is written directly (no MCP wrapper yet — future `agentboard_save_phase` subsumes this).

---

## Design notes (why this structure)

- **Complexity Check is flag-only (not gate).** The F4 anti-pattern was `Case 2: scope reduction` prompting the user to cut scope here. That silently overrode Phase 4 scope commitment. Now the flag just triggers optional eng-review; scope stays owned by intent.
- **Single Responsibility is enforced, not suggested.** "and" / "with" in a purpose sentence is a direct split trigger. This prevents god-files that accumulate reasons to change.
- **UI hook is conditional on real `ui_surface`.** Keyword scan excludes out_of_scope_guard so deletions / "TUI work belongs to F3" annotations don't trigger false positives (the F4 bug).
- **Riskiest assumption → edge case** — one hop from frame keeps the attack surface visible. If the riskiest assumption never shows up in edge_cases, the plan is flinching.
- **`--deep=eng` is the default depth expansion.** Most non-trivial goals benefit; user can opt in. `design` / `devex` are narrower triggers.
- **No `--deep=ceo`** — scope-level depth belongs in intent, not architecture. Splitting would reintroduce scope-decision duplication (F4 anti-pattern).

---

## Freeze notice

Default skill routing still runs the legacy gauntlet. This skill executes only when explicitly invoked OR when upstream `agentboard-frame` hands off. See `memory/feedback_freeze_gauntlet_flow.md`.
