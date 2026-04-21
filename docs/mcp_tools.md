# MCP Tools — M1a-data pile read surface

Agent Dev Board v3 exposes a read-only pile API via MCP. These tools let
any agent framework (Claude Code, OpenHands, Codex, custom) resume a
past agent run with bounded token cost and without parsing raw JSONL.

## `agentboard_get_session(rid: str)`

Returns the run's `session.md` — a ≤500-token index with per-chapter
teasers, status line, and As-Is → To-Be delta placeholder. This is the
agent's **discovery surface**: a fresh Claude Code session calling this
tool with only `rid` learns which chapter to load next.

### Response

Success:
```json
{
  "status": "ok",
  "rid": "run_abc",
  "content": "---\nschema_version: 1\n---\n# goal-title\n\n## Chapters\n- **contract**: ...\n- **labor**: ...\n- **verdict**: ...\n- **delta**: ...\n\n**Status**: iter N/M · phase `...` · last verdict `...`\n"
}
```

Errors:
```json
{"status": "error", "code": "RID_NOT_FOUND", "rid": "...", "hint": "rid not in .rid_index.json"}
{"status": "error", "code": "PILE_ABSENT", "rid": "...", "gid": "...", "hint": "Run is orphan — run `agentboard rebuild-pile <gid>` (M1a-plumbing CLI)"}
```

## `agentboard_get_chapter(rid: str, chapter: str)`

Returns the named chapter markdown (≤3k tok). `chapter` param is a
JSON-schema enum: `"contract" | "labor" | "verdict" | "delta"`.
Input is normalized (strip + lowercase) before lookup.

### Response

Success:
```json
{"status": "ok", "rid": "run_abc", "chapter": "labor", "content": "# Chapter — Labor\n\n_5 iterations · run `run_abc`_\n\n- iter 1 · tdd_red · 0.1s · RED (0P/1F)\n..."}
```

Errors:
```json
{"status": "error", "code": "CHAPTER_NOT_FOUND", "valid_chapters": ["contract", "labor", "verdict", "delta"], "hint": "..."}
{"status": "error", "code": "RID_NOT_FOUND", ...}
```

## `agentboard_log_decision(..., rid?: str, gid?: str)` — pile sibling write (M1a-data extension)

Existing tool gains two opt-in kwargs. When both `rid` and `gid` are
passed, the dispatch writes a companion `iter.json` under
`runs/<rid>/iters/iter-NNN.json` in addition to the usual
`decisions.jsonl` append.

```json
{
  "project_root": "...",
  "task_id": "t_...",
  "iter": 7,
  "phase": "tdd_green",
  "reasoning": "...",
  "verdict_source": "GREEN_CONFIRMED",
  "rid": "run_abc",       // opt-in for pile
  "gid": "g_..."          // opt-in for pile
}
```

Legacy callers (no `rid`) see unchanged behavior — backward compatible.

## Example agent workflow

A fresh Claude Code session resuming prior work:

```python
# 1. Load session index — 500 tok max
session = await call_tool("agentboard_get_session", {"project_root": root, "rid": rid})

# Parse status line to know how far the run got
# Parse teasers to decide which chapter to load

# 2. Load the specific chapter the task needs — 3k tok max
labor = await call_tool("agentboard_get_chapter", {
    "project_root": root, "rid": rid, "chapter": "labor"
})

# 3. Decide whether to resume, replay, or branch
```

Total token cost for full context restore: ≤3.5k tokens (vs. parsing
raw `decisions.jsonl` + multiple `changes/iter_N.diff` files which can
easily exceed 20k tokens).

## Telemetry

Every MCP tool call appends a row to `.devboard/mcp_calls.jsonl`:

```json
{"tool": "agentboard_get_session", "ts": "2026-04-22T...", "duration_ms": 12, "bytes_returned": 487, "rid": "run_abc"}
```

Used by future `agentboard-retro` to validate Premise #1 (from CEO
review): "agents need session history via MCP." If the log shows zero
calls after 2 weeks of usage, the pile infrastructure is unused and
should be simplified.

## Error response schema (lock)

All errors return a structured dict with consistent fields:

| Field | Type | Meaning |
|--|--|--|
| `status` | `"error"` | sentinel |
| `code` | `"PILE_ABSENT" \| "RID_NOT_FOUND" \| "CHAPTER_NOT_FOUND" \| "BAD_RID"` | machine-readable discriminator |
| `hint` | string | actionable next step for the caller |
| `rid` / `gid` / `chapter` | string (when resolvable) | context |
| `valid_chapters` | array (CHAPTER_NOT_FOUND only) | enum enumeration |
