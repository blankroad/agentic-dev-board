# agentic-dev-board — Claude Code guide

## Architecture

```
src/devboard/
  mcp_server.py      — 22 MCP tools (state mgmt, plan lock, verify, iron law). No LLM calls.
  cli.py             — Typer CLI: init, board (TUI), watch, timeline, decisions, replay, retro
  models.py          — Pydantic models: LockedPlan, AtomicStep, BoardState, Goal
  storage/
    file_store.py    — All disk I/O. atomic_write + fcntl write-locks. Single source of truth.
  gauntlet/
    lock.py          — build_locked_plan: parse Decide JSON → LockedPlan + SHA256 hash
    pipeline.py      — run_gauntlet: 5 LLM steps (Frame→Scope→Arch→Challenge→Decide)
  agents/
    iron_law.py      — check_iron_law: detect Write/Edit before test write (TDD enforcement)
  analytics/
    docgen.py        — PR descriptions, Confluence pages, wiki docs from LockedPlan
  replay/
    replay.py        — branch_run: create new run from a checkpoint iteration
  orchestrator/      — [LEGACY] LangGraph graph. Not imported by CLI or MCP server.

skills/              — Claude Code skill SKILL.md files
hooks/               — PostToolUse hooks: iron-law-check.sh, danger-guard.sh, activity-log.py
tests/               — 277 tests. Run: pytest
```

## Invariants

- MCP server never calls an LLM. State management and deterministic verification only.
- `compute_hash` covers: problem, non_goals, scope_decision, architecture, goal_checklist, atomic_steps.
- `atomic_write` + rename guarantees crash-safe file writes.
- `file_lock` uses `fcntl.flock(LOCK_EX)` on writes; reads currently unprotected (see TODOS.md).

## Running tests

```bash
pip install -e .
pytest                      # full suite (277 tests)
pytest tests/test_mcp.py    # MCP tools only
```

## MCP server

Start: `devboard-mcp` (runs on stdio, Claude Code connects automatically via `.mcp.json`).
All 22 tools are in `mcp_server.py:call_tool`. Add new tools in `list_tools()` + dispatch block.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.

Key routing rules:
- Brainstorm a feature goal → invoke `devboard-brainstorm`
- Build a locked plan → invoke `devboard-gauntlet`
- Implement a locked plan with TDD → invoke `devboard-tdd`
- Security / CSO review → invoke `devboard-cso`
- Final approval + PR → invoke `devboard-approval`
- Post-sprint retro → invoke `devboard-retro`
- CEO / architecture review → invoke `plan-ceo-review`
- Bugs, errors → invoke `investigate`

## Key files to read before touching

| Area | File |
|------|------|
| Plan locking / hash | `src/devboard/gauntlet/lock.py`, `src/devboard/models.py:108` |
| MCP tool dispatch | `src/devboard/mcp_server.py:call_tool` |
| File I/O safety | `src/devboard/storage/file_store.py` |
| Iron Law check | `src/devboard/agents/iron_law.py` |
| TDD skill | `skills/devboard-tdd/SKILL.md` |

## Known deferred issues

See `TODOS.md` — especially `install.sh` branch hardcoding (fix before merging to main).
