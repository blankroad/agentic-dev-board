---
name: agentboard-plan
description: D3 entry point (2026-04-23, replaces agentboard-gauntlet). Thin orchestrator that runs the D1 phase chain (intent → frame → architecture → stress → lock) for any non-trivial build / implement / add / create / refactor request. Each phase hands off to the next via its own Skill invocation, so this orchestrator is intentionally minimal — set up the goal, kick off intent, and let the chain run. After lock, the chain continues automatically into agentboard-execute for TDD and then agentboard-parallel-review + agentboard-approval.
when_to_use: User asks to build, implement, add, create, make, or extend anything involving more than one file, tests, auth, payments, sessions, databases, APIs, architecture decisions, or anything destined for main/production. User says "plan this", "design this", "architect this", "how should we approach X", "rethink Y". MANDATORY before agentboard-execute for non-trivial work. Skip only for typo fixes, pure config tweaks, or when the user explicitly says "skip planning".
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

> **Status (2026-04-23, D3 cutover):** Canonical planning entry point. Replaces `agentboard-gauntlet` (deprecated). Routes any "build / implement / plan" request into the D1 phase chain. The legacy `agentboard-gauntlet` + `agentboard-brainstorm` + `agentboard-tdd` skills carry DEPRECATED banners and stay on disk for retro / replay compatibility with pre-cutover goals, but new work should never invoke them directly.

You are the **Planning Orchestrator** — a thin router that starts the D1 phase chain. You do not do planning work yourself. You set up the goal, pick the entry point (fresh start vs resume), and invoke the first phase skill. Each phase hands off to the next, so your job ends after kickoff.

## Preamble — Project Guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

- `MISSING` → print "agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill." and exit immediately.
- `OK` → proceed.

## Step 1 — Goal setup

Call `agentboard_list_goals(project_root)`:

- **0 goals on the board** → call `agentboard_add_goal(project_root, title, description)` with the user's prompt. Use the first sentence of the prompt as the title, the full prompt as the description. The returned `goal_id` becomes this session's target.
- **Active goal exists, user's prompt matches it** (semantic match on title/description) → reuse the active goal_id. Don't double-create.
- **User's prompt describes something new** (doesn't match any existing goal's title/description) → `agentboard_add_goal` to create a fresh goal; it becomes the target.
- **Multiple goals, no active one, prompt is ambiguous** → `AskUserQuestion`: list top 5 most recent goal titles + "create new goal" option. Let the user pick.

Output: `Planning goal: {title} ({goal_id})`.

## Step 2 — Pick the entry point

Scan `.devboard/goals/<goal_id>/` to determine where in the chain we already are:

| Artifact present | Meaning | Entry point |
|---|---|---|
| None (or only `goal.json`) | Fresh goal, never planned | `agentboard-intent` |
| `brainstorm.md` exists, no `gauntlet/frame.md` | Intent done, frame not started | `agentboard-frame` |
| `brainstorm.md` + `frame.md` exist, no `arch.md` | Up to frame, architecture not started | `agentboard-architecture` |
| ... + `arch.md`, no `challenge.md` | Up to architecture, stress not started | `agentboard-stress` |
| ... + `challenge.md`, no `plan.json` | Up to stress, lock not started | `agentboard-lock` |
| `plan.json` exists (plan locked) | Plan already locked | See Step 3 below |

### If the user invoked `agentboard-plan` with "rethink" / "replan" / "revise"

Override the above and route back to the appropriate phase. If the user names a phase ("rethink architecture"), route to that phase. If they say "rethink" generically, ask which phase: intent / frame / architecture / stress / lock. Any phase re-run re-writes downstream artifacts too (subsequent phases will re-read upstream and re-produce their own output).

## Step 3 — If plan.json already exists

Three branches:

1. **Task + run already started, not yet converged** — invoke `agentboard-execute` to continue the R-G-R loop. (This is the "resume after session interruption" path.)
2. **Task converged, not yet approved** — invoke `agentboard-parallel-review` (if not yet run) or `agentboard-approval` (if review is CLEAN).
3. **Task approved + pushed** — nothing to do. Output `Goal {goal_id} already shipped. Use "rethink" to replan a new iteration on top.` and exit.

State detection:

- `agentboard_load_decisions(project_root, task_id)` → inspect latest `phase` entry:
  - `phase="approval"` + `verdict_source="PUSHED"` or `"MERGED"` → branch 3 (shipped)
  - `phase="parallel_review"` + `overall="CLEAN"` → branch 2 (approval)
  - `phase="review"` + `verdict_source="PASS"` → branch 2 (parallel-review)
  - Any `tdd_*` or `execute` entry, no `review` → branch 1 (resume execute)

## Step 4 — Invoke the entry point

Based on Step 2's decision, invoke ONE skill via the `Skill` tool:

```
Skill(agentboard-intent, "goal_id=<goal_id> project_root=<project_root>")
# or agentboard-frame / -architecture / -stress / -lock / -execute / -parallel-review / -approval
```

Each phase skill knows how to load its upstream artifacts + hand off to the next. This orchestrator's job is done once the entry skill starts.

### `--deep` pass-through

If the user invoked `agentboard-plan --deep=<mode>`, forward the flag to the target phase skill when it matches (intent: `ceo` / `officehours`; architecture: `eng` / `design` / `devex`; stress: `codex`). If the `--deep` mode isn't valid for the target phase, output a message and ignore the flag:

```
--deep=<mode> is not supported for phase <X>. Supported modes:
  intent: --deep=ceo, --deep=officehours
  architecture: --deep=eng, --deep=design, --deep=devex
  stress: --deep=codex
Proceeding without --deep.
```

## Step 5 — Log orchestrator dispatch

```
agentboard_log_decision(
    project_root, task_id=<if available, else empty>,
    iter=0,
    phase="plan",
    reasoning=f"dispatched to <skill> (entry detected: <fresh|resume from phase X|replan request>)",
    verdict_source="DISPATCHED",
)
```

If no `task_id` yet (fresh goal pre-lock), omit `task_id` from the call — the phase skills will start the task at lock time.

## Required MCP calls

| When | Tool |
|---|---|
| Step 1 — check existing goals | `agentboard_list_goals(project_root)` |
| Step 1 — new goal needed | `agentboard_add_goal(project_root, title, description)` |
| Step 3 — resume state detection | `agentboard_load_decisions(project_root, task_id)` |
| Step 4 — entry invoke | `Skill(agentboard-<phase>, ...)` |
| Step 5 — audit | `agentboard_log_decision(phase="plan", verdict_source="DISPATCHED")` |

## The D1 chain after this orchestrator

```
agentboard-plan (orchestrator, YOU ARE HERE)
   ↓ invokes the first incomplete phase
agentboard-intent (scope authority, writes brainstorm.md YAML frontmatter)
   ↓ invokes frame
agentboard-frame (assumptions + success criteria, writes frame.md)
   ↓ invokes architecture
agentboard-architecture (file structure + UI hook + ENG_REVIEW flag)
   ↓ invokes stress (optionally via eng-review)
agentboard-stress (adversarial plan review, 4+ failure modes)
   ↓ invokes lock
agentboard-lock (LockedPlan + SHA256 + start_task + metadata)
   ↓ invokes execute
agentboard-execute (R-G-R loop with Iron Law + Preemptive Defense Checklist)
   ↓ invokes parallel-review
agentboard-parallel-review (CSO + redteam, in parallel)
   ↓ invokes approval on CLEAN
agentboard-approval (PR body, push, merge)
```

Each step is a separate skill with its own SKILL.md. Read their files for the detailed spec. This orchestrator does not replicate their content.

## Design notes

- **Thin by design.** The phase chain already has inter-phase handoffs wired up (intent → frame, frame → architecture, etc.). An orchestrator that re-implements the chain would duplicate that wiring. All this skill needs to do is pick the right entry point and kick off.
- **Entry-point detection is observable.** Scanning `.devboard/goals/<goal_id>/` for phase artifacts gives a deterministic resume point without needing a state machine. Files as truth (P3 State > Conversation).
- **`--deep` pass-through keeps depth opt-in per phase.** The user writes one flag on the orchestrator; we forward it to the phase it applies to. No magic routing.
- **No planning work happens here.** If you find yourself reasoning about scope / assumptions / architecture in this skill — STOP. That belongs in intent / frame / architecture.
- **Plan already exists → resume, don't re-plan.** Invoking `agentboard-plan` on a locked goal doesn't re-lock; it routes to execute / parallel-review / approval depending on state. Users who want to replan use the "rethink" verb explicitly.

## Freeze status

The freeze directive on `agentboard-gauntlet` / `agentboard-tdd` / `agentboard-brainstorm` was lifted at D3 cutover (2026-04-23). Those skills stay on disk as DEPRECATED for retro / replay compatibility with pre-cutover goals; their SKILL.md files carry deprecation banners pointing here. New work uses this skill as the canonical planning entry.
