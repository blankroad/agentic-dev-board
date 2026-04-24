---
name: agentboard-dep-audit
description: Use when approval Step 0 needs a dependency CVE check, or when the user says "dep audit", "check vulns", "audit deps", "security audit deps". Runs agentboard_check_dependencies and verdicts CLEAN / VULNERABLE based on CRITICAL/HIGH findings.
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

Before any other action, verify agentboard is initialized in this project. Run this Bash command:

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
```

- Output `MISSING` → print this message to the user and **exit the skill immediately** (do NOT call any MCP tools, do NOT proceed with any steps below):
  > agentboard is not initialized in this project. Run `agentboard init && agentboard install` first to enable this skill.
- Output `OK` → proceed with the skill below.

You are the **Dependency Auditor**. Reviewer and CSO have finished. Your only job: catch known CVEs in the dependency tree before push.

## Step 1 — Run audit

```
agentboard_check_dependencies(project_root)
```

Response shape: `{ecosystem, auditor, severity_counts, findings, skipped_reason}`.

## Step 2 — Interpret

### A. skipped_reason is set

```
## Dep Audit: SKIPPED

Reason: {skipped_reason}
```

- "no supported lockfile" → verdict CLEAN (nothing to audit)
- "pip-audit not found" / "npm not found" → verdict CLEAN (can't audit, do not block push), but output one-line warning suggesting install
- "auditor timed out" → verdict CLEAN with warning; suggest re-run
- "auditor output not json" → verdict CLEAN with warning; the auditor itself is broken

### B. Findings present

- CRITICAL ≥ 1 OR HIGH ≥ 1 → verdict **VULNERABLE**
- Only MEDIUM / LOW → verdict **CLEAN** (output as advisory; approval proceeds)

## Step 3 — Output

```
## Dep Audit

Ecosystem: {ecosystem} | Auditor: {auditor}
Severity: CRITICAL={n} HIGH={n} MEDIUM={n} LOW={n}

### Findings (top 5)
- {package} ({severity}) — {id or via}
...

### Verdict: CLEAN | VULNERABLE
```

## On VULNERABLE

1. Log decision with verdict_source='VULNERABLE' via `agentboard_log_decision`
2. Checkpoint `dep_audit_complete` with `{verdict: VULNERABLE, critical, high}`
3. Refuse to hand off to approval — respond to user with the list of CVEs and suggested fix versions
4. User fixes deps → re-run skill

## On CLEAN

1. Log decision with verdict_source='CLEAN'
2. Checkpoint `dep_audit_complete` with `{verdict: CLEAN, ...}`
3. Hand off to `agentboard-approval` (or return to caller)

## Required MCP calls

| When | Tool |
|---|---|
| Step 1 | `agentboard_check_dependencies(project_root)` |
| After verdict | `agentboard_checkpoint(project_root, run_id, "dep_audit_complete", {verdict, severity_counts, skipped_reason})` |
| After verdict | `agentboard_log_decision(project_root, task_id, iter=N, phase="dep_audit", reasoning=<summary>, verdict_source="CLEAN"|"VULNERABLE")` |
