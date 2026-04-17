# agentic-dev-board

> **Claude Code Skills + MCP server + hooks** that enforce a rigorous agentic dev workflow:
> Planning Gauntlet → TDD Red-Green-Refactor → multi-perspective review → Approval.

<p align="center">
  <img alt="tests" src="https://img.shields.io/badge/tests-218%20passed-brightgreen" />
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-blue" />
  <img alt="skills" src="https://img.shields.io/badge/skills-9-purple" />
  <img alt="mcp tools" src="https://img.shields.io/badge/MCP%20tools-22-purple" />
  <img alt="hooks" src="https://img.shields.io/badge/hooks-2-orange" />
</p>

Uses your **Claude Max subscription** (not per-token API billing). Works in Claude Code; portable to any skill-aware agent (OpenCode, Copilot CLI) via the markdown skills.

---

## What this is

Two years of "how do I make an LLM actually ship good code?" compressed into:

- **9 Skills** — markdown playbooks Claude Code auto-loads per context
- **22 MCP tools** — deterministic state/verify/approval operations
- **2 Hooks** — Iron Law + DangerGuard, always-on safety
- **CLI** — observability (TUI, retro, watch, audit), installer, time-travel replay

Influences:
- **[obra/superpowers](https://github.com/obra/superpowers)** — Iron Law of TDD, 4-phase RCA, evidence-over-claims
- **[gstack](https://github.com/garrytan/gstack)** — 5-step Planning Gauntlet, CSO security review, retro, careful

---

## TL;DR — get running

**One-line installer** (clones to `~/.local/share/agentic-dev-board`, adds `devboard` alias to your shell rc, installs 9 skills globally):

```bash
curl -fsSL https://raw.githubusercontent.com/blankroad/agentic-dev-board/mcp-migration/install.sh | bash
```

Then:
```bash
source ~/.zshrc    # or open a new terminal

cd ~/my-project
devboard init            # .devboard/ scaffold
devboard install         # writes .claude/{hooks,settings.json} + .mcp.json (Python auto-detected)

claude                   # open Claude Code — skills + MCP tools auto-load
# You: "build calculator.py with add/sub/mul/div and pytest, div-by-zero raises"
# Claude Code: devboard-gauntlet → locks plan → devboard-tdd → R-G-R → devboard-approval
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
curl -fsSL https://raw.githubusercontent.com/blankroad/agentic-dev-board/mcp-migration/install.sh | bash
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Claude Code — conversational orchestrator (uses your subscription)  │
│                                                                      │
│   ↓ auto-loads skills per user prompt                                │
│                                                                      │
│  .claude/skills/devboard-*/SKILL.md                                  │
│   brainstorm → gauntlet → tdd → cso → redteam → rca → approval      │
│   retro, replay                                                      │
│                                                                      │
│   ↓ skills call MCP tools for state + verify                         │
│                                                                      │
│  devboard MCP server (local subprocess)                              │
│   devboard_lock_plan()        — SHA256 hash + plan.md               │
│   devboard_verify()           — deterministic pytest runner         │
│   devboard_log_decision()     — decisions.jsonl append              │
│   devboard_check_iron_law()   — TDD violation detection             │
│   devboard_check_command_safety() — DangerGuard pattern match       │
│   devboard_build_pr_body(), devboard_push_pr()                      │
│   devboard_save_learning(), devboard_search_learnings()             │
│   devboard_generate_retro(), devboard_replay()                      │
│   ... 22 tools total                                                 │
│                                                                      │
│   ↓ hooks run independently of skills                                │
│                                                                      │
│  .claude/hooks/                                                      │
│   danger-guard.sh      — PreToolUse Bash — blocks rm -rf / etc      │
│   iron-law-check.sh    — PostToolUse Write|Edit — TDD reminders     │
│                                                                      │
│  devboard CLI (observability, no LLM calls)                          │
│   init | install | board | watch | retro | audit | replay | mcp     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## The 9 Skills

| Skill | Activates when | Enforces |
|---|---|---|
| `devboard-brainstorm` | Goal is short/vague | Up to 5 Socratic questions before planning |
| `devboard-gauntlet` | New goal needs planning | Frame → Scope → Arch → Challenge → Decide, locks with SHA256 hash |
| `devboard-tdd` | Code changes | Iron Law of TDD + Red-Green-Refactor + atomic_steps |
| `devboard-cso` | Diff touches auth/crypto/sql/subprocess | OWASP Top 10 + STRIDE at 7/10 confidence gate |
| `devboard-redteam` | After PASS, before commit | Adversarial QA — 3+ breaking scenarios |
| `devboard-rca` | RETRY verdict or test failure | 4-phase root cause (no quick fixes) |
| `devboard-approval` | Loop converged | Diff summary + squash policy + PR body + `gh pr create` |
| `devboard-retro` | Periodic / on request | Aggregate decisions across goals + runs |
| `devboard-replay` | "try different approach from iter N" | Time-travel branch from checkpoint |

---

## The 22 MCP Tools

### State — init, goals, plans
`devboard_init` · `devboard_add_goal` · `devboard_list_goals` · `devboard_update_task_status` · `devboard_lock_plan` · `devboard_load_plan`

### Decisions & diffs
`devboard_log_decision` · `devboard_load_decisions` · `devboard_save_iter_diff`

### Verification & safety
`devboard_verify` (deterministic pytest) · `devboard_check_iron_law` · `devboard_check_command_safety`

### Approval & push
`devboard_get_diff_stats` · `devboard_build_pr_body` · `devboard_apply_squash_policy` · `devboard_push_pr`

### Learnings
`devboard_save_learning` · `devboard_search_learnings` · `devboard_relevant_learnings`

### Retro & replay
`devboard_generate_retro` · `devboard_list_runs` · `devboard_replay`

All tools are **stateless** (read/write `.devboard/` directly) and **LLM-free** (Claude Code does the reasoning).

---

## The 2 Hooks

| Hook | Event | Action |
|---|---|---|
| `danger-guard.sh` | `PreToolUse` on `Bash` | `rm -rf /` / fork bomb / `dd of=/dev/*` → **deny**. `git push --force` / `DROP TABLE` / `curl \| sh` → **ask** |
| `iron-law-check.sh` | `PostToolUse` on `Write\|Edit` | If production file written with no matching test file anywhere in repo → emits TDD reminder via `systemMessage` |

Hooks work **independently of skills** — even if `devboard-tdd` isn't loaded, you get Iron Law reminders and DangerGuard blocks.

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

**No `devboard run`** — that role now belongs to Claude Code + skills.

---

## Philosophy

6 pillars (inherited from the pre-MCP architecture):

1. **Honest over hopeful** — no "should work" claims; verify fresh
2. **Decisions are first-class artifacts** — *why* is queryable via `decisions.jsonl`
3. **The loop is the product** — quality comes from iteration + review + reflection
4. **Human as orchestrator** — Claude Code is the conversation, you can redirect anytime
5. **Time-reversible** — every state transition checkpointed, any iteration replayable
6. **Local trust, remote ceremony** — loose locally, strict at `git push` / PR boundary

On top of these, the Superpowers/gstack-inspired enforcements:

- **Iron Law of TDD** — no production code without a failing test first
- **Evidence over claims** — `devboard_verify` runs real pytest, not just reasoning
- **Systematic debugging** — 4-phase RCA, no quick fixes
- **Confidence-gated security** — CSO reports findings only at ≥7/10 confidence
- **Escalation on repeat failure** — 3× same symptom → rerun Gauntlet, not more iterations

---

## Storage layout

```
.devboard/
├── state.json                   # board index (goals, active_goal)
├── config.yaml
├── goals/<goal_id>/
│   ├── plan.md                  # LockedPlan (human-readable)
│   ├── plan.json                # machine-readable
│   ├── gauntlet/{frame,scope,arch,challenge,decide}.md
│   └── tasks/<task_id>/
│       ├── task.md
│       ├── task.json
│       ├── changes/iter_1.diff, iter_2.diff, ...
│       └── decisions.jsonl      # why every decision was made
├── learnings/<name>.md          # frontmatter: tags, category, confidence
├── runs/<run_id>.jsonl          # every state transition checkpoint
└── retros/retro_<ts>.md
```

`.gitignore` auto-adds `.devboard/runs/`, `.devboard/state.json`, `.devboard/goals/` (content is typically ephemeral or regenerable; `learnings/` and `retros/` are worth committing if shared).

---

## Example flow (in Claude Code)

```
You: "build calculator.py with add/sub/mul/div, div-by-zero raises, pytest suite"

Claude Code auto-loads devboard-gauntlet:
  Frame:  Problem extracted, non-goals listed, wedge = "4 pure functions + 1 pytest file"
  Scope:  HOLD (goal is well-scoped)
  Arch:   calculator.py single module + test_calculator.py
  Challenge: finds 2 CRITICAL (div-by-zero, float return type)
  Decide: JSON with atomic_steps (4 behaviors, each 1 test + 1 impl)
  → calls devboard_lock_plan() → SHA256 hash, plan.md saved

Claude Code auto-loads devboard-tdd:
  RED step s_001: write test_add() → run pytest → fails "NameError: add"
    → calls devboard_log_decision(phase="tdd_red", verdict="RED_CONFIRMED")
  GREEN step s_001: write def add → pytest passes
    → calls devboard_verify() → all items matched, full_suite_passed
    → calls devboard_log_decision(phase="tdd_green", verdict="GREEN_CONFIRMED")
  REFACTOR: nothing to clean → SKIPPED
  ... repeat for s_002, s_003, s_004 (sub, mul, div-by-zero)

Claude Code checks CSO:
  Diff has no auth/crypto/sql keywords → skip

Claude Code auto-loads devboard-redteam:
  Attack scenarios: Unicode division? Mixed int/float? Negative zero?
  Verdict: SURVIVED

Claude Code auto-loads devboard-approval:
  Shows: diff stats + 4/4 checklist + 4 iter, 0 retries
  "Squash policy [1-4]?"  You: 1
  "Push? [y/N]?"  You: y
  → calls devboard_build_pr_body() → devboard_push_pr() → PR URL
```

All of this is **observable** in:
- Claude Code's own UI (tool calls, outputs)
- `.devboard/runs/<run_id>.jsonl` (every transition)
- `.devboard/tasks/.../decisions.jsonl` (every *why*)
- `devboard watch` (live tail)
- `devboard retro` (periodic aggregation)

---

## Testing

```bash
pytest -v                  # 218 tests passing
pytest tests/test_mcp.py   # MCP server + install tests
pytest tests/test_phase_h.py  # CSO + DangerGuard + retro + learnings v2
pytest tests/test_phase_g.py  # TDD cycle + verify + 4-phase RCA
```

Tests are organized by the "phases" that introduced each feature (A–H); the MCP migration is the current phase and tests live in `test_mcp.py`.

---

## What's in `src/devboard/`?

```
src/devboard/
├── cli.py                    # Typer CLI (observability + installer)
├── mcp_server.py             # MCP stdio server — 22 tools
├── install.py                # copy skills/hooks, emit .mcp.json + settings.json
├── config.py                 # DevBoardConfig + TDDConfig
├── models.py                 # Pydantic: Goal, Task, LockedPlan, AtomicStep, DecisionEntry
├── gauntlet/lock.py          # build_locked_plan + SHA256 hashing
├── orchestrator/
│   ├── verify.py             # deterministic pytest runner → VerificationReport
│   ├── approval.py           # PR body builder + squash policies
│   ├── push.py               # git push + gh pr create
│   ├── checkpointer.py       # JSONL append-only
│   ├── interrupt.py          # HintQueue (HITL, still usable)
│   ├── state.py, runner.py, graph.py   # legacy LangGraph (deprecated)
├── agents/
│   ├── iron_law.py           # TDD violation detector
│   ├── router.py             # cost-aware model tier routing (unused in MCP path)
│   ├── tdd.py, cso.py, redteam.py, reflect.py, systematic_debug.py, planner.py,
│       executor.py, reviewer.py, base.py   # legacy — parsers still useful
├── tools/
│   ├── careful.py            # DangerGuard pattern library
│   ├── fs.py, shell.py, git.py, base.py   # legacy — deprecated in favor of Claude Code's built-ins
├── storage/file_store.py     # .devboard/ I/O
├── memory/learnings.py       # frontmatter-based, tagged
├── memory/retriever.py       # keyword + tag + confidence scoring
├── analytics/retro.py        # retrospective aggregation
├── replay/replay.py          # time-travel branching
└── tui/                      # Textual observability board
```

**Legacy code is preserved on the `main` branch** (pre-MCP). The MCP migration lives on `mcp-migration`.

---

## License

MIT.
