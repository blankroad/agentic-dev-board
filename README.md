# agentic-dev-board

> **Claude Code Skills + MCP server + hooks** that enforce a rigorous agentic dev workflow:
> Brainstorm → Planning Gauntlet → Plan Approval → TDD Red-Green-Refactor → Review → Approval.

<p align="center">
  <img alt="tests" src="https://img.shields.io/badge/tests-292%20passed-brightgreen" />
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-blue" />
  <img alt="skills" src="https://img.shields.io/badge/skills-9-purple" />
  <img alt="mcp tools" src="https://img.shields.io/badge/MCP%20tools-30-purple" />
  <img alt="hooks" src="https://img.shields.io/badge/hooks-3-orange" />
  <img alt="ci" src="https://github.com/blankroad/agentic-dev-board/actions/workflows/ci.yml/badge.svg" />
</p>

Uses your **Claude Max subscription** (not per-token API billing). Works in Claude Code; portable to any skill-aware agent (OpenCode, Copilot CLI) via the markdown skills.

---

## What this is

Two years of "how do I make an LLM actually ship good code?" compressed into:

- **9 Skills** — markdown playbooks Claude Code auto-loads per context
- **30 MCP tools** — deterministic state/verify/approval operations (zero LLM calls)
- **3 Hooks** — Iron Law + DangerGuard + Activity Log, always-on safety
- **CLI** — observability (TUI, retro, watch, audit), installer, time-travel replay
- **Analytics** — Kanban board, Confluence/JIRA/wiki doc generation, PR descriptions, metrics

Influences:
- **[obra/superpowers](https://github.com/obra/superpowers)** — Iron Law of TDD, 4-phase RCA, evidence-over-claims
- **[gstack](https://github.com/garrytan/gstack)** — 5-step Planning Gauntlet, CSO security review, retro, careful

---

## TL;DR — get running

**One-line installer** (clones to `~/.local/share/agentic-dev-board`, adds `devboard` alias to your shell rc, installs 9 skills globally):

```bash
curl -fsSL https://raw.githubusercontent.com/blankroad/agentic-dev-board/main/install.sh | bash
```

Then:
```bash
source ~/.zshrc    # or open a new terminal

cd ~/my-project
devboard init            # .devboard/ scaffold
devboard install         # writes .claude/{hooks,settings.json} + .mcp.json (Python auto-detected)

claude                   # open Claude Code — skills + MCP tools auto-load
# You: "build calculator.py with add/sub/mul/div and pytest, div-by-zero raises"
# Claude Code: devboard-brainstorm → devboard-gauntlet → approve → devboard-tdd → devboard-approval
```

**Manual install** (if you prefer not to curl|bash):
```bash
git clone https://github.com/blankroad/agentic-dev-board.git
cd agentic-dev-board
python -m venv .venv && source .venv/bin/activate
pip install -e .
devboard install --scope global     # skills → ~/.claude/skills/
echo "alias devboard=\"$PWD/.venv/bin/devboard\"" >> ~/.zshrc
```

**Update** (re-run the one-liner — it's idempotent):
```bash
curl -fsSL https://raw.githubusercontent.com/blankroad/agentic-dev-board/main/install.sh | bash
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Claude Code — conversational orchestrator (uses your subscription)      │
│                                                                          │
│   ↓ auto-loads skills per user prompt                                    │
│                                                                          │
│  .claude/skills/devboard-*/SKILL.md                                      │
│   brainstorm → gauntlet → [plan approval] → tdd → cso → redteam         │
│   → rca → approval → retro, replay                                       │
│                                                                          │
│   ↓ skills call MCP tools for state + verify (no LLM inside MCP)        │
│                                                                          │
│  devboard MCP server (local subprocess, 30 tools)                        │
│   devboard_save_brainstorm()   — save premises/risks/alternatives       │
│   devboard_approve_plan()      — sign off plan before locking           │
│   devboard_lock_plan()         — SHA256 hash + plan.md (requires ✓)    │
│   devboard_verify()            — deterministic pytest runner            │
│   devboard_log_decision()      — decisions.jsonl append                 │
│   devboard_check_iron_law()    — TDD violation detection                │
│   devboard_checkpoint()        — run state snapshot                     │
│   devboard_metrics()           — convergence/retry/iron-law stats       │
│   devboard_build_pr_body()     — PR body from plan + decisions          │
│   devboard_generate_retro()    — sprint retrospective                   │
│   devboard_replay()            — time-travel branch from checkpoint     │
│   ... 30 tools total                                                     │
│                                                                          │
│   ↓ hooks run independently of skills                                    │
│                                                                          │
│  .claude/hooks/                                                          │
│   danger-guard.sh      — PreToolUse Bash  — blocks rm -rf / etc        │
│   iron-law-check.sh    — PostToolUse Write|Edit — TDD reminders        │
│   activity-log.py      — PostToolUse all  — append every tool call     │
│                                                                          │
│  devboard CLI (observability, no LLM calls)                              │
│   init | install | board | watch | retro | audit | replay | mcp         │
│                                                                          │
│  devboard analytics (Kanban, Confluence, JIRA, wiki, PR, metrics)        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## The 9 Skills

| Skill | Activates when | Enforces |
|---|---|---|
| `devboard-brainstorm` | Goal is short/vague | Up to 5 Socratic questions + saves brainstorm output via `devboard_save_brainstorm` |
| `devboard-gauntlet` | New goal needs planning | Frame → Scope → Arch → Challenge → Decide, **Plan Review gate**, locks with SHA256 hash |
| `devboard-tdd` | Code changes | Iron Law of TDD + Red-Green-Refactor + atomic_steps |
| `devboard-cso` | Diff touches auth/crypto/sql/subprocess | OWASP Top 10 + STRIDE at 7/10 confidence gate |
| `devboard-redteam` | After PASS, before commit | Adversarial QA — 3+ breaking scenarios |
| `devboard-rca` | RETRY verdict or test failure | 4-phase root cause (no quick fixes) |
| `devboard-approval` | Loop converged | Diff summary + squash policy + PR body + `gh pr create` |
| `devboard-retro` | Periodic / on request | Aggregate decisions across goals + runs |
| `devboard-replay` | "try different approach from iter N" | Time-travel branch from checkpoint |

### Skill flow

```
User prompt
    │
    ▼
devboard-brainstorm   ← vague goal? up to 5 Socratic questions
    │                    saves brainstorm.md + brainstorm-{ts}.md (versioned)
    ▼
devboard-gauntlet     ← 5-step planning (Frame→Scope→Arch→Challenge→Decide)
    │                    presents plan for review
    ▼
devboard_approve_plan ← user signs off (or requests revision of specific step)
    │
devboard_lock_plan    ← SHA256 hash locked — immutable from here
    │
    ▼
devboard-tdd          ← Red-Green-Refactor per atomic_step
    │                    logs RED/GREEN/RETRY decisions + checkpoints
    ▼
devboard-cso (if security-sensitive diff)
devboard-redteam (adversarial QA)
devboard-rca (if 3× same symptom)
    │
    ▼
devboard-approval     ← squash policy → push → PR URL
```

---

## The 30 MCP Tools

### State — init, goals, plans
| Tool | Purpose |
|---|---|
| `devboard_init` | Scaffold `.devboard/`, update `.gitignore` |
| `devboard_add_goal` | Register a goal on the board |
| `devboard_list_goals` | List all goals with status |
| `devboard_save_brainstorm` | Save brainstorm output (latest alias + versioned copy) |
| `devboard_approve_plan` | Record plan approval/revision decision before locking |
| `devboard_lock_plan` | SHA256 hash plan, write plan.md + plan.json (requires prior approval) |
| `devboard_load_plan` | Load locked plan for a goal |
| `devboard_verify_plan_integrity` | Re-compute hash, detect plan tampering |
| `devboard_start_task` | Create Task + start run. Returns `{task_id, run_id}` |
| `devboard_update_task_status` | Update task lifecycle state |

### Execution & decisions
| Tool | Purpose |
|---|---|
| `devboard_checkpoint` | Append state snapshot to run JSONL |
| `devboard_log_decision` | Append decision entry to decisions.jsonl |
| `devboard_load_decisions` | Load all decisions for a task |
| `devboard_save_iter_diff` | Archive per-iteration diff |
| `devboard_resume_run` | Find last checkpoint, determine what's next |

### Verification & safety
| Tool | Purpose |
|---|---|
| `devboard_verify` | Run pytest, match checklist items to test output |
| `devboard_check_iron_law` | Detect production file write without prior test write |
| `devboard_check_command_safety` | DangerGuard pattern match on shell commands |

### Approval & push
| Tool | Purpose |
|---|---|
| `devboard_get_diff_stats` | `git diff --stat` against HEAD |
| `devboard_build_pr_body` | Generate PR description from plan + decisions |
| `devboard_apply_squash_policy` | Reshape commits (squash / semantic / preserve) |
| `devboard_push_pr` | `git push` + `gh pr create` |

### Learnings
| Tool | Purpose |
|---|---|
| `devboard_save_learning` | Save a learning with tags, category, confidence |
| `devboard_search_learnings` | Keyword + tag search |
| `devboard_relevant_learnings` | Retrieve learnings relevant to current context |

### Retro, metrics, replay
| Tool | Purpose |
|---|---|
| `devboard_generate_retro` | Sprint retrospective markdown (per-goal + aggregate) |
| `devboard_metrics` | Convergence rate, retry rate, Iron Law hits, skill activation |
| `devboard_diagnose` | Skill activation audit — finds gaps in workflow compliance |
| `devboard_list_runs` | List all runs with status |
| `devboard_replay` | Branch run from iteration N with variant note |

All tools are **stateless** (read/write `.devboard/` directly) and **LLM-free** (Claude Code does the reasoning).

---

## The 3 Hooks

| Hook | Event | Action |
|---|---|---|
| `danger-guard.sh` | `PreToolUse` on `Bash` | `rm -rf /` / fork bomb / `dd of=/dev/*` → **deny**. `git push --force` / `DROP TABLE` / `curl \| sh` → **ask** |
| `iron-law-check.sh` | `PostToolUse` on `Write\|Edit` | Production file written with no matching test file → emits TDD reminder via `systemMessage` |
| `activity-log.py` | `PostToolUse` on all tools | Appends every tool call + result to `.devboard/activity.jsonl` for trial-and-error review |

Hooks work **independently of skills** — even if `devboard-tdd` isn't loaded, you get Iron Law reminders and DangerGuard blocks.

---

## Analytics outputs

The `devboard.analytics` module produces human-readable artifacts from `.devboard/` state — no extra LLM calls.

### Kanban board

```
# Kanban Board — 3 goals

## Pushed (1)
- ✓ Core CRUD  `g_20260418_...`  — plan locked, 3 iter, 1 retry

## Active (2)
- · Search & Tags  `g_20260418_...`  — plan locked, 1 iter, 1 retry, RETRY
- · Export         `g_20260418_...`  — plan locked
```

Column is derived from task status (pushed/converged/awaiting_approval/blocked), not goal.status — so it reflects actual work state.

Formats: `render_terminal()` (Rich ANSI), `render_markdown()` (wiki paste), `render_jira()` (JIRA wiki markup).

### Design doc / Confluence page

One call to `collect_doc(store, goal_id)` produces a `DesignDoc` that renders to:

- **Markdown** (`to_markdown()`) — PR description, GitHub wiki
- **Confluence wiki markup** (`to_confluence()`) — paste directly into Confluence editor
- **JIRA wiki markup** (`to_jira()`) — paste into JIRA ticket description

Contents per goal:
- Problem, Architecture, Scope & Budget
- Success Criteria checklist — `[x]` if task is pushed/converged, `[ ]` if in progress
- Atomic steps with test + impl file paths
- Full development arc: iteration-by-iteration RED/GREEN/RETRY decisions with reasoning
- Known failure modes (from Gauntlet Challenge step)
- Artifacts (files touched, PR URL if pushed)

```confluence
h1. Core CRUD
h2. Development Arc

h3. Iteration 2
* *Review* — *RETRY*
  ** s_004 duplicate check: IntegrityError not propagated
  ** → let IntegrityError bubble up instead of catching

h3. Iteration 3
* *Tdd Green* — *GREEN_CONFIRMED*
  ** removed try/except — IntegrityError propagates. 4/4 pass.
```

### Metrics

```
Goals: 3  |  Runs: 2 (converged: 1, rate: 50%)
Iterations: 4  |  Retry rate: 100%
Iron Law hits: 0  |  RCA escalations: 0  |  CSO VULNERABLE: 0
Verdicts: GREEN_CONFIRMED ×4, RED_CONFIRMED ×3, RETRY ×2
```

---

## CLI

```bash
devboard init              # scaffold .devboard/
devboard install           # install skills + hooks + .mcp.json
  --scope global           #   → ~/.claude/skills/ (no hooks/mcp, those are per-project)
  --no-hooks --no-mcp      #   pick & choose
  --overwrite              #   replace existing

devboard goal add "..."    # register a goal (auto-active if first)
devboard goal list         # Kanban-style goal table
devboard task show <id>    # task detail with decision timeline

devboard board             # Textual TUI
devboard watch [--run ID]  # tail .devboard/runs/*.jsonl live
devboard retro             # markdown retro report
  --goal ID | --last-n N
  --save                   # → .devboard/retros/retro_<ts>.md
devboard audit             # self-DX check (install state, tool versions, API key)

devboard replay <run_id> --from <N> --variant "..."   # time-travel branch
devboard learnings list
devboard learnings search [QUERY] --tag T --category C

devboard mcp               # start MCP server stdio (Claude Code spawns this automatically)
devboard config KEY VALUE  # set config (e.g., tdd.enabled false)
```

**No `devboard run`** — that role belongs to Claude Code + skills.

---

## Example flow (in Claude Code)

```
You: "I want to add search to the bookmarks app"

Claude auto-loads devboard-brainstorm (goal is vague):
  → 4 clarifying questions (success criteria, storage, scope boundary, runtime)
  You answer → calls devboard_save_brainstorm() → brainstorm.md saved

Claude auto-loads devboard-gauntlet:
  Frame:  Problem extracted, non-goals listed
  Scope:  HOLD (well-scoped after brainstorm)
  Arch:   search.py module + tags table, SQLite FTS or LIKE
  Challenge: finds 2 HIGH (FTS vs LIKE perf, tag schema design)
  Decide: JSON with atomic_steps (3 behaviors)

  → presents plan for review
  "Approve to lock? (yes / no + step to revise: problem|scope|arch|challenge)"
  You: yes
  → calls devboard_approve_plan(approved=True)
  → calls devboard_lock_plan() → SHA256 hash, immutable

Claude auto-loads devboard-tdd:
  RED s_001: write test_search_url() → pytest fails "ImportError: no module search"
    → devboard_checkpoint(tdd_red_complete) + devboard_log_decision(RED_CONFIRMED)
  GREEN s_001: write search() → pytest passes
    → devboard_verify() → devboard_checkpoint(tdd_green_complete)
  RETRY on s_002: tag schema wrong → devboard_log_decision(RETRY)
  ... fix + GREEN → converged

Claude auto-loads devboard-approval:
  Diff stats + 3/3 checklist ✓ + 2 iter, 1 retry
  "Squash policy [1-4]?" → 1 (squash)
  "Push? [y/N]?" → y
  → devboard_push_pr() → PR URL logged
```

All of this is observable in:
- Claude Code's UI (tool calls, outputs)
- `.devboard/runs/<run_id>.jsonl` (every state transition)
- `.devboard/goals/<goal_id>/tasks/.../decisions.jsonl` (every *why*)
- `devboard watch` (live tail)
- `devboard retro` / `devboard metrics` (aggregation)
- `devboard analytics` Confluence/JIRA doc (full development arc)

---

## Storage layout

```
.devboard/
├── state.json                       # board index (goals, active_goal)
├── activity.jsonl                   # every tool call (from activity-log hook)
├── goals/<goal_id>/
│   ├── goal.json
│   ├── brainstorm.md                # latest brainstorm output
│   ├── brainstorm-{ts}.md           # versioned copies (one per brainstorm run)
│   ├── plan_review.json             # {status: approved|revision_pending, ts}
│   ├── plan.md                      # LockedPlan (human-readable)
│   ├── plan.json                    # machine-readable + SHA256 hash
│   ├── gauntlet/{frame,scope,arch,challenge}.md
│   └── tasks/<task_id>/
│       ├── task.md
│       ├── task.json
│       ├── changes/iter_1.diff, iter_2.diff, ...
│       └── decisions.jsonl          # why every decision was made
├── learnings/<name>.md              # frontmatter: tags, category, confidence
├── runs/<run_id>.jsonl              # every state transition checkpoint
└── retros/retro_<ts>.md
```

`.gitignore` auto-adds `.devboard/runs/`, `.devboard/state.json`, `.devboard/goals/`. `learnings/` and `retros/` are worth committing if shared with a team.

---

## Security

- **`_sanitize_id()`** — all `goal_id` and `task_id` inputs to `FileStore` are validated against path traversal (`..`, `/`, `\`) before being used as filesystem paths.
- **`atomic_write()`** — all file writes use temp file + `os.replace()` so readers never see partial writes.
- **`file_lock()`** — `fcntl.flock(LOCK_EX)` on writes to prevent races between concurrent Claude Code sessions.
- **Plan integrity** — `devboard_verify_plan_integrity` re-computes SHA256 over `problem + non_goals + scope_decision + architecture + goal_checklist + atomic_steps` and compares to stored hash. Detects any post-lock modification.
- **Approval gate** — `devboard_lock_plan` refuses if `plan_review.json` is missing or `status != approved`. Plans cannot be locked without explicit sign-off.

---

## Philosophy

6 pillars:

1. **Honest over hopeful** — no "should work" claims; `devboard_verify` runs real pytest, every time
2. **Decisions are first-class artifacts** — *why* is queryable via `decisions.jsonl`; the arc is readable in Confluence
3. **The loop is the product** — quality comes from iteration + review + reflection
4. **Human as orchestrator** — Claude Code is the conversation; you redirect, approve, and sign off
5. **Time-reversible** — every state transition checkpointed; any iteration replayable via `devboard_replay`
6. **Local trust, remote ceremony** — loose locally, strict at `git push` / PR boundary

Superpowers/gstack-inspired enforcements on top:

- **Iron Law of TDD** — no production code without a failing test first
- **Evidence over claims** — `devboard_verify` runs real pytest, not just reasoning
- **Systematic debugging** — 4-phase RCA, no quick fixes
- **Confidence-gated security** — CSO reports findings only at ≥7/10 confidence
- **Escalation on repeat failure** — 3× same symptom → rerun Gauntlet, not more iterations
- **Approval gates** — brainstorm before plan, sign-off before lock, CSO before push

---

## Testing

```bash
pytest                         # 292 tests
pytest tests/test_mcp.py       # MCP tools + install (147 tests)
pytest tests/test_file_store.py  # FileStore I/O + brainstorm + plan review
pytest tests/test_iron_law.py  # Iron Law detector (Write/Edit/fs_write)
pytest tests/test_skills.py    # SKILL.md content contracts
pytest tests/test_e2e_flow.py  # full end-to-end scenarios
pytest tests/test_phase_k.py   # crash recovery + resume
pytest tests/test_phase_m.py   # metrics + diagnose
```

CI runs Python 3.11 + 3.12 on every push to `main` (`.github/workflows/ci.yml`).

---

## What's in `src/devboard/`?

```
src/devboard/
├── cli.py                    # Typer CLI (observability + installer)
├── mcp_server.py             # MCP stdio server — 30 tools (no LLM calls)
├── install.py                # copy skills/hooks, emit .mcp.json + settings.json
├── models.py                 # Pydantic: Goal, Task, LockedPlan, AtomicStep, DecisionEntry
├── gauntlet/lock.py          # build_locked_plan + SHA256 hashing
├── storage/
│   ├── file_store.py         # .devboard/ I/O — atomic_write, file_lock, _sanitize_id
│   └── base.py               # Repository ABC
├── analytics/
│   ├── kanban.py             # Kanban board (terminal/markdown/JIRA) — task-status-aware columns
│   ├── docgen.py             # Design doc (markdown/Confluence/JIRA) — full development arc
│   └── metrics.py            # Convergence/retry/Iron Law stats + skill activation
├── agents/
│   └── iron_law.py           # TDD violation detector (Write/Edit/fs_write tool names)
├── orchestrator/
│   ├── verify.py             # deterministic pytest runner → VerificationReport
│   ├── approval.py           # PR body builder + squash policies
│   ├── push.py               # git push + gh pr create
│   ├── checkpointer.py       # JSONL append-only checkpoint log
│   └── [legacy: state.py, runner.py, graph.py, interrupt.py]
├── memory/
│   ├── learnings.py          # frontmatter-based, tagged
│   └── retriever.py          # keyword + tag + confidence scoring
├── replay/replay.py          # time-travel branching from checkpoint
└── tui/                      # Textual observability board
```

Legacy modules (`orchestrator/graph.py`, `agents/router.py`, etc.) are preserved for reference but not imported by the CLI or MCP server.

---

## License

MIT.
