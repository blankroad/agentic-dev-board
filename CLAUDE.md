# agentboard — Claude Code Guide

## Mission

**agentboard is the fleet control tower for agent coding.** It locks intent across many parallel AI agent sessions, enforces execution, and turns their history into a reusable asset.

Three words: **Fleet** (N agents, not 1) · **Intent Lock** (SHA256-hashed LockedPlan; drift is prevented mechanically) · **History as Asset** (past decisions feed future sessions).

## The Bet

Agent coding is moving from 1-at-a-time to N-in-parallel. What the developer needs then is not "a deeper thinking AI" but **infrastructure to observe, compare, and reuse N agents**. Every design call flows from this assumption:

| Assumption | Consequence |
|---|---|
| A developer runs 3–10 agent sessions concurrently | TUI fleet view is required |
| Every session's decisions / failures / learnings are reusable | `decisions.jsonl`, `save_learning`, retro are required |
| "Why did this agent do X?" must be answerable weeks later | `replay` + checkpoint are required |
| Agent creativity causes drift | hash lock + `iron_law` + `out_of_scope_guard` are required |

## Core Principles

All design debates are adjudicated against these. When in doubt, apply them.

### P1. Structured > Free-form

Every phase output must be machine-parseable (YAML frontmatter + named fields). If TUI / retro / replay / cross-agent compare cannot parse it, the fleet vision does not hold. Deep-mode bodies may still contain free prose, but the metadata layer is always structured.

### P2. Enforce > Persuade

Rules that matter are enforced by hooks, hashes, and gates — not by prompts asking "please". LLMs forget rules across long conversations; only mechanical enforcement is trustworthy. Examples: `iron_law.py` PostToolUse hook, `compute_hash`, `out_of_scope_guard`, `atomic_write`. Explicit escape hatches (e.g., `BLOCKER_OVERRIDDEN`) are allowed but must be logged.

### P3. State > Conversation

The source of truth is the `.devboard/` filesystem + MCP tools — not chat history. Chat is volatile and unreproducible; files are permanent and readable by every client. Current state → `agentboard_get_session`. Past decisions → `decisions.jsonl`. Plan → `plan.json`. When a skill needs context, it reads the file, not the transcript.

### P4. Observable by Default

Every **phase** (intent / frame / architecture / … — NOT every TDD cycle) emits `phase_start` / `phase_end` events to `decisions.jsonl`. Missing events are bugs. This is what lets the fleet view answer "what is agent B doing right now?" Add new phases only with event logging wired in from the first commit.

### P5. History is Input, not Output

Past-session artifacts (`learnings`, `decisions`, `plan.md`, retro outputs) are **first-class inputs** to the next session — not museum exhibits. Cold start on goal 1; compounding value from goal N onward. Examples: `search_learnings`, `relevant_learnings`, Frame auto-injecting relevant constraints.

### P6. Means ≠ End

Quality mechanisms (TDD, linting, type checking, hash locking) are **internal infrastructure — never user-facing value**. "How many red-green cycles ran?" does not substitute for "what decision was made and why?" Applied:

- retro / fleet view MUST NOT surface iteration counts, test cycles, retry rates as primary indicators
- Such metrics are debug / diagnostic only — optional detail tab at most
- User-facing aggregation is about **decisions + outcomes + patterns**

This is why `agentboard-synthesize-report` is described as "release notes, NOT a TDD journey recap" and why `dev_review` reads "phase totals, NOT raw iter reasoning".

## What agentboard is NOT (anti-scope)

Prevents scope creep by calling out confusions people actually have.

| NOT | Use instead / why |
|---|---|
| A CI/CD pipeline | pre-push gates only (`integration_test_command` + push + PR). Downstream CI stays as-is |
| A project management tool (Linear / Jira replacement) | `goals` exist to lock intent, not manage a backlog. No velocity, sprints, or assignments |
| A general observability platform (Datadog replacement) | scoped to agent coding sessions. Production runtime observability is out |
| An agent-building framework / platform (LangGraph / CrewAI / AutoGen replacement) | agentboard is an **application** running on Claude Code, not a platform for building agents. Extension is via new skill files, not a Python DSL or plugin API |

## Relationships with Other Tools

| Tool | Relation | Why |
|---|---|---|
| gstack `plan-*-review`, `office-hours`, `autoplan` | **Absorb** via agentboard `--deep` modes (roadmap) | Retrofitting them for fleet-awareness is infeasible; they are single-session |
| gstack `codex`, `ship`, `investigate`, `qa`, `land-and-deploy` | **Coexist** — independent responsibilities | General-purpose tools; no reason to absorb |
| superpowers (obra) | **Inspiration** — phase-gate + self-review patterns already absorbed | Single-session origin; we extend to fleet |
| Claude Code (CLI, IDE, desktop) | **Host** | Claude Code is the agent's body; agentboard is its state + policy |
| LangGraph / CrewAI / AutoGen | **Non-dependency** (removed in 82c19c3) | "State + policy" philosophy conflicts with graph-orchestrator frameworks |
| Codex CLI | **Coexist** — callable from `--deep=codex` modes (roadmap) | "200 IQ second opinion" is a role Codex does better than agentboard |

## Success Signals

agentboard is successful when all of the following become routine:

1. A single developer runs **5+ agent sessions concurrently**, observing all of them via the TUI fleet view
2. A learning from a goal completed 3 weeks ago **auto-injects into today's Frame phase**, preventing a repeat mistake
3. An agent attempting to modify an `out_of_scope` file is **automatically blocked**, and retro reveals where in the phase chain the drift originated
4. A single retro surfaces the last 30 days of **decision patterns** — why scope was decided this way, which failure reasons recurred, which trade-offs were avoided — and this reshapes the next goal's starting point
5. The user naturally says "I don't need `plan-ceo-review` — `intent --deep=ceo` is enough"

---

## Architecture

```
src/agentboard/
  mcp_server.py      — MCP tools (state mgmt, plan lock, verify, iron law). No LLM calls.
  cli.py             — Typer CLI: init, board (TUI), watch, timeline, decisions, replay, retro
  models.py          — Pydantic models: LockedPlan, AtomicStep, BoardState, Goal
  storage/
    file_store.py    — All disk I/O. atomic_write + fcntl write-locks. Single source of truth.
  gauntlet/
    lock.py          — build_locked_plan: parse Decide JSON → LockedPlan + SHA256 hash
    pipeline.py      — run_gauntlet: test-only simulator of the 5-step chain (NOT the production path; the production chain is the SKILL.md executed by Claude Code)
    steps/           — frame.py, scope.py, arch.py, challenge.py, decide.py, brainstorm.py
                       Currently only used by the pipeline.py test simulator. Candidates for removal
                       as the planning-layer redesign lands (see Known deferred issues)
  agents/
    iron_law.py      — check_iron_law: detect Write/Edit before test write (TDD enforcement)
  analytics/
    docgen.py        — PR descriptions, Confluence pages, wiki docs from LockedPlan
    overview_payload.py — Build OverviewPayload for TUI center-panel tabs from on-disk artifacts
  replay/
    replay.py        — branch_run: create new run from a checkpoint iteration
  orchestrator/      — approval / checkpointer / push / verify / state helpers used by
                       mcp_server.py, replay, retro. The LangGraph graph + runner + HintQueue
                       were removed in the cleanup; only live helpers remain.

skills/              — Claude Code skill SKILL.md files (the production execution path)
hooks/               — PostToolUse hooks: iron-law-check.sh, danger-guard.sh, activity-log.py
tests/               — 738+ tests. Run: pytest
```

## Invariants

- MCP server never calls an LLM. State management + deterministic verification only.
- `compute_hash` covers: `problem`, `non_goals`, `scope_decision`, `architecture`, `goal_checklist`, `atomic_steps`.
- `atomic_write` + rename guarantees crash-safe file writes.
- `file_lock` uses `fcntl.flock(LOCK_EX)` on writes; reads currently unprotected (see TODOS.md).
- The production Gauntlet path is the SKILL.md read by Claude Code. There is no Python pipeline; `gauntlet/pipeline.py` and `gauntlet/steps/` were removed in F4 (landed 2026-04-23).
- `agentboard-brainstorm` is the **single scope authority**. `brainstorm.md` emits YAML frontmatter with `scope_mode` / `refined_goal` / `wedge` / `req_list` / `alternatives_considered` / `rationale` / `user_confirmed`. The gauntlet reads that frontmatter and injects `scope_mode` into `LockedPlan.scope_decision` verbatim — it does NOT re-decide scope.

## Running tests

```bash
pip install -e .
pytest                      # full suite
pytest tests/test_mcp.py    # MCP tools only
```

## MCP server

Start: `agentboard-mcp` (runs on stdio; Claude Code connects automatically via `.mcp.json`).
All tools are in `mcp_server.py:call_tool`. Add new tools in `list_tools()` + the dispatch block.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it via the Skill tool as your FIRST action. Do NOT answer directly and do NOT use other tools first.

Key routing rules:

- Brainstorm a feature goal → `agentboard-brainstorm`
- Build a locked plan → `agentboard-gauntlet`
- Implement a locked plan with TDD → `agentboard-tdd`
- Security / CSO review → `agentboard-cso`
- Final approval + PR → `agentboard-approval`
- Post-sprint retro → `agentboard-retro`
- Bugs, errors → `investigate` or `agentboard-rca`

> **F4 landed (2026-04-23):** The triplicate scope-decision gates are gone. `agentboard-brainstorm` Phase 4 RECOMMENDATION is the single scope authority, emitted as YAML frontmatter in `brainstorm.md`. `agentboard-gauntlet` is now 4 steps (Frame → Arch → Challenge → Decide) — Step 2 Scope is deleted, and Step 3 Complexity Check only sets `ENG_REVIEW_NEEDED`, never prompts for scope reduction. If a user wants to revise scope at the plan-review gate, they return to brainstorm Phase 4 rather than the gauntlet.

## Key files to read before touching

| Area | File |
|---|---|
| Plan locking / hash | `src/agentboard/gauntlet/lock.py`, `src/agentboard/models.py` (LockedPlan) |
| MCP tool dispatch | `src/agentboard/mcp_server.py` (`call_tool`) |
| File I/O safety | `src/agentboard/storage/file_store.py` |
| Iron Law check | `src/agentboard/agents/iron_law.py` |
| TDD skill | `skills/agentboard-tdd/SKILL.md` |
| Fleet view | `src/agentboard/tui/` (Screen, event stream, heat grid) |
| TUI Overview payload | `src/agentboard/analytics/overview_payload.py` |

## Known deferred issues

See `TODOS.md` for tracked items.

**Planning-layer redesign roadmap (revised 2026-04-23, D-first):**

### M0 ✅ F4 landed (2026-04-23, merge `dd3b75b`)

Brainstorm YAML frontmatter contract; gauntlet Step 2 Scope deleted; Complexity Check reduced to `ENG_REVIEW_NEEDED` flag only; `scope_decision` injected from `brainstorm.md`; dead code removed (`gauntlet/steps/`, `gauntlet/pipeline.py`, `llm/prompts/gauntlet/`). **The current `agentboard-gauntlet` chain is now FROZEN** — do not invoke for new work (see `memory/feedback_freeze_gauntlet_flow.md`).

### D1 — Phase-skill skeletons (TOP PRIORITY)

Build new phase skills in parallel with the frozen gauntlet (no disruption until D3 cutover). Each skill outputs YAML-frontmatter-first artifacts so later observability layers can parse without retrofit.

- **D1a `agentboard-intent`** — discover + commit to scope (replaces `agentboard-brainstorm` eventually). Writes `brainstorm.md` YAML frontmatter (already defined by F4).
- **D1b `agentboard-frame`** — surface hidden assumptions + riskiest assumption + success criteria. Reads `brainstorm.md` frontmatter. No scope decisions (owned by intent).
- **D1c `agentboard-architecture`** — file structure, test strategy, `critical_files`, `out_of_scope_guard`. UI hook + design-review gate when `ui_surface=true`. Complexity Check emits `ENG_REVIEW_NEEDED` only.
- **D1d `agentboard-stress`** — adversarial plan review (4+ failure modes). Reads prior phases.
- **D1e `agentboard-lock`** — atomic_steps decomposition, SHA256 hash via `build_locked_plan`, writes `plan.md` + `plan.json`. Mechanical (no LLM re-decision).

### D2 — `--deep` modes (gstack absorption)

Layered on D1 skills. Each `--deep` flag expands the phase with a specific depth rubric imported from gstack:

- `intent --deep=ceo` ← `plan-ceo-review` (10x scope thinking, 4 modes)
- `intent --deep=officehours` ← `office-hours` (YC 6 forcing questions)
- `architecture --deep=eng` ← `plan-eng-review` (architecture coherence, test strategy, diagrams)
- `architecture --deep=design` / `visual --deep=design` ← `plan-design-review` (0-10 rating per dimension, for `ui_surface`)
- `architecture --deep=devex` ← `plan-devex-review` (persona, magical moments)
- `stress --deep=codex` ← `codex challenge` (200 IQ adversarial)

All depth-mode outputs remain structured (YAML frontmatter compliant). See `memory/reference_gstack_absorption.md`.

### D3 — Orchestrator + cutover

- Thin `agentboard-plan` skill chains `intent → frame → architecture → (visual?) → stress → lock`.
- `agentboard-gauntlet` is deprecated and renamed; CLAUDE.md skill routing updated to point at the new chain.
- `agentboard-brainstorm` is deprecated in favor of `agentboard-intent`.
- The freeze directive lifts automatically once D3 cutover lands.

### C — Observability layer (after D, deferred)

Because D1 skills already emit YAML-frontmatter artifacts, this layer is additive not invasive:

- **C1** — `phase_start` / `phase_end` events in `decisions.jsonl` (each phase skill already prepared to emit)
- **C2** — TUI `phases` tab consuming the event stream + artifacts

### Housekeeping (orthogonal, address when convenient)

- **H0** `save_brainstorm` validation hardening (3 MEDIUM findings from F4 redteam) — **may be obsoleted** by D1a since `agentboard-intent` will own the write path.
- **B0** `atomic_write` alias-vs-versioned concurrency race (pre-existing, affects `file_store.py` broadly) — **promote to D1-prerequisite** if D1 skills reuse the same `atomic_write` pattern; alternatively fix the pattern in a shared helper that D1 skills adopt from day 1.

`install.sh` branch hardcoding: fix before merging to main.
