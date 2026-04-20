# TODOS — mcp-migration branch

Items deferred from CEO review (2026-04-18). Fix before or shortly after merging to main.

## CRITICAL — fix before merge

- [ ] **install.sh: hardcoded branch** (`install.sh:5`) — `BRANCH="mcp-migration"` must become `BRANCH="${AGENTIC_DEV_BOARD_BRANCH:-main}"` before merging to main.

## HIGH — fix soon after merge

- [ ] **mcp_server.py:633 silent exception** — `except Exception: pass  # non-fatal` swallows task status update failures. Add `logger.warning(...)` so errors surface in activity log.

- [ ] **mcp_server.py module split** — 946-line single file. Split into `tools/plans.py`, `tools/tasks.py`, `tools/verify.py`, etc. No behavior change, just maintainability.

## MEDIUM

- [ ] **load_board() read lock** (`file_store.py:85`) — No `fcntl.LOCK_SH` on reads. Low risk for single-user dev tool, but could cause stale reads with concurrent sessions. Add shared read lock to `load_board()`.

- [ ] **replay event-name mismatch** (`replay.py:28`) — `find_state_at_iteration` silently returns `None` if checkpoint events use unexpected names. Add a "no iteration_complete events found in this run" error message to distinguish from "run not found".

- [ ] **verify checklist fuzzy matching** — `devboard_verify` matches checklist items to pytest output by keyword. Items phrased differently from test names will always be `unmatched`. Consider adding a checklist-to-test mapping field to `AtomicStep`.

## LOW / FUTURE

- [ ] **brainstorm.md in retro output** — `agentboard-retro` doesn't surface brainstorm premises/risks. Track as separate issue once brainstorm feature lands.

- [ ] **concurrent session: stale board state** — same as load_board read lock above; low priority.

---

## Design doc implementation (next sprint)

From approved design: `~/.gstack/projects/cli-dev-board/ctmctm-mcp-migration-design-20260418-094718.md`

- [ ] `mcp_server.py` — add `devboard_save_brainstorm` tool
- [ ] `mcp_server.py` — add `devboard_approve_plan` tool
- [ ] `storage/file_store.py` — add `save_brainstorm()` / `load_brainstorm()` methods
- [ ] `skills/agentboard-brainstorm/SKILL.md` — 3-phase deep brainstorm (Premise Challenge → Alternatives → Save+handoff)
- [ ] `skills/agentboard-gauntlet/SKILL.md` — Plan Review gate before `devboard_lock_plan`
- [ ] `tests/test_mcp.py` — tests for both new tools
- [ ] Resolve 5 Reviewer Concerns from design doc before implementing
