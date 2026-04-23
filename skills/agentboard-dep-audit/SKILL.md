---
name: agentboard-dep-audit
description: Use when approval Step 0 needs a dependency CVE check, or when the user says "dep audit", "check vulns", "audit deps", "security audit deps". Runs agentboard_check_dependencies and verdicts CLEAN / VULNERABLE based on CRITICAL/HIGH findings.
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
