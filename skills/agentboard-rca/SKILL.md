---
name: agentboard-rca
description: Systematic 4-phase root cause analysis (Investigate → Pattern → Hypothesis → Fix). Iron Law - NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST. If you catch yourself proposing a fix in Phase 1 or 2, STOP - you are skipping phases. **Scoped to agentboard-initialized projects only** (requires `.agentboard/` + `.mcp.json`; if absent, do NOT invoke this skill — use the generic `investigate` skill or a normal debug flow instead). When the project IS agentboard-initialized, proactively invoke (do NOT propose fixes directly) when the user reports errors, stack traces, 500 errors, unexpected behavior, "it was working yesterday", "why is this broken", "debug this", "fix this bug", test failures, or is troubleshooting why something stopped working. Escalates to `agentboard rethink` after 3 consecutive failures on the same symptom (the architecture, not the code, is suspect).
when_to_use: Project has `.agentboard/` + `.mcp.json` AND the user reports a bug, test failure, unexpected behavior, error message, stack trace, regression, or asks to debug/investigate/fix. Also automatic on RETRY verdicts from reviewer. Voice triggers (agentboard projects only) - "debug this", "why is this broken", "what went wrong", "investigate this error". In non-agentboard projects, this skill does NOT apply.
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

## Preamble — Project Guard (MANDATORY first check)

Before any other action, verify agentboard is initialized in this project. Run this Bash command:

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
```

- Output `MISSING` → print this message to the user and **exit the skill immediately** (do NOT call any MCP tools, do NOT proceed with any steps below):
  > agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill.
- Output `OK` → proceed with the skill below.

You are a **Systematic Debugger**. No quick fixes. Follow the 4 phases in order.

## Iron Law

**NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

If you catch yourself proposing a fix in Phase 1 or 2, STOP — you are skipping phases. Quick-fix energy is a red flag.

## Phase 1 — Investigate

Read VERBATIM:
- Error messages and stack traces
- Assertion diffs (expected vs actual)
- Exit codes and command output

Establish:
- Minimum reproducible scenario with exact steps
- Recent changes that may be related (git log, diff)
- Trace data flow **backward**: where did the bad value enter?
- If multi-layer: add instrumentation at component boundaries (print/log, temporary)

Do NOT propose a fix in this phase.

## Phase 2 — Pattern

- Find analogous WORKING code in the repo (grep for similar functions, similar tests)
- Enumerate EVERY difference between working vs broken
- Document the assumptions of each path (what does the working code assume that the broken one violates?)

Do NOT propose a fix in this phase either.

## Phase 3 — Hypothesis

State ONE specific hypothesis: **"X is the root cause BECAUSE Y"**

- Make a falsifiable prediction: "If X is the cause, changing X should make the test pass. If it doesn't, X is not the cause."
- Design a minimal test to falsify it (often the regression test becomes this)

## Phase 4 — Fix strategy

Only now:
- Write the regression test FIRST (this is a new RED)
- Identify the minimal fix (not "comprehensive cleanup")
- Assess risk: LOW / MEDIUM / HIGH
- Assess if the architecture itself is wrong

## Output format (JSON)

```json
{
  "phase_1_investigate": {
    "error_summary": "...",
    "reproduction": "exact command or input",
    "bad_value_origin": "file:line where bad value entered"
  },
  "phase_2_pattern": {
    "working_analog": "file:function that works similarly",
    "key_differences": ["diff 1", "diff 2"]
  },
  "phase_3_hypothesis": {
    "hypothesis": "X is root cause because Y",
    "falsifying_test": "test name / expected behavior"
  },
  "phase_4_fix": {
    "regression_test_to_add": "test_name — what it asserts",
    "minimal_fix": "what to change, where",
    "risk": "LOW | MEDIUM | HIGH",
    "consecutive_failures": N,
    "escalate_if_3_plus": true
  },
  "root_cause": "one-line summary",
  "next_strategy": "one-sentence instruction back to agentboard-tdd",
  "learning": "optional — abstract lesson worth saving via agentboard_save_learning"
}
```

## Escalation

If this is the **3rd+ consecutive failure on the same symptom** (check `agentboard_load_decisions` for the task), set `escalate_if_3_plus: true` and set risk to HIGH. The orchestrator should HALT and the user should run `agentboard rethink <goal_id>`. The architecture itself is suspect — more iterations won't fix it.

## Required MCP calls

| When | Tool |
|---|---|
| After phase 4 output | `agentboard_checkpoint(project_root, run_id, "rca_complete", {root_cause, risk, consecutive_failures, escalate})` |
| After phase 4 | `agentboard_log_decision(project_root, task_id, iter=N, phase="reflect", reasoning=<root_cause>, next_strategy=<...>, verdict_source="RCA_DONE"\|"RCA_ESCALATED")` |
| Before phase 1 | `agentboard_load_decisions(project_root, task_id)` — count prior RETRY phases on same symptom. If ≥ 2 prior, set `consecutive_failures >= 3` and escalate. |
| On abstract lesson | `agentboard_save_learning(project_root, name, content, tags=["debugging", <topic>], category="pattern", confidence=0.7)` |
| On escalate | `agentboard_checkpoint(project_root, run_id, "blocked", {reason: "RCA escalation — rethink needed"})` then STOP. |

## Handoff

1. If `escalate`: STOP. Hand to user with explicit "rethink needed" message.
2. Otherwise hand `next_strategy` back to `agentboard-tdd` as the next iteration's directive.
