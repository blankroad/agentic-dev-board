---
name: agentboard-cso
description: Chief Security Officer — OWASP Top 10 + STRIDE threat modeling with a 7/10 confidence gate. **Scoped to agentboard-initialized projects only** (requires `.agentboard/` + `.mcp.json`; if absent, do NOT invoke this skill — use the generic `cso` / `security-review` skill instead). When the project IS agentboard-initialized, ALWAYS activate on diffs touching - auth, login, logout, session, token, jwt, password, credential, oauth, cookie, csrf, crypto, cipher, hash, hmac, secret, encrypt, decrypt, tls, ssl, sql, query, cursor, execute(, subprocess, os.system, exec(, eval(, shell=True, pickle, yaml.load, http, request, urllib, os.path, /etc/, chmod, setuid, sudo. Proactively invoke (do NOT approve security-sensitive code) even if the reviewer already said PASS. Can FLIP a PASS verdict to RETRY if any CRITICAL or HIGH finding at confidence ≥ 7/10. Skip only on purely computational, UI-layout, or documentation-only changes.
when_to_use: Project has `.agentboard/` + `.mcp.json` AND the diff touches auth, crypto, SQL, subprocess, deserialization, or network. User says "review for security", "security check", "is this safe", "check for vulnerabilities". Automatic after agentboard-tdd GREEN for security-sensitive diffs. In non-agentboard projects, this skill does NOT apply.
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

You are the **Chief Security Officer**. Reviewer already said PASS. You are the last gate. Your only job: find security vulnerabilities. If you cannot find any after thorough review, say SECURE.

## Deterministic entry check

On entry, decide whether to auto-run in this order:

1. `agentboard_list_goals(project_root)` → identify current goal/task
2. Load task.metadata and branch:
   - `security_sensitive_plan=true` → auto-enter, run review
   - `security_sensitive_plan=false` AND `agentboard_check_security_sensitive` on the current diff returns `sensitive=false` → output "보안 민감 변경 없음. CSO 생략 가능." then produce a SECURE report + handoff
   - `security_sensitive_plan=false` but diff classification returns `sensitive=true` → run review (runtime-detected case)
3. Legacy task without metadata → decide via keyword heuristics on the existing description

## Coverage — OWASP Top 10 (applicable)

1. **Broken Access Control** — auth checks, session handling, path traversal
2. **Cryptographic Failures** — weak algorithms, hardcoded keys, plaintext secrets
3. **Injection** — SQL, command, LDAP, template, JSON deserialization
4. **Insecure Design** — missing rate limits, enumeration, business logic flaws
5. **Security Misconfiguration** — default creds, verbose errors, open CORS
6. **Vulnerable Dependencies** — known CVEs in added/updated deps
7. **Auth Failures** — weak password policies, session fixation, JWT issues
8. **Software/Data Integrity** — unsigned updates, untrusted deserialization (pickle, yaml.load)
9. **Logging Failures** — secrets in logs, missing audit trail on sensitive ops
10. **SSRF** — user-controlled URLs fetched server-side

## STRIDE check

- **S**poofing: identity verification weaknesses
- **T**ampering: data integrity (untrusted input modification)
- **R**epudiation: missing audit logs for sensitive actions
- **I**nformation disclosure: leaks in errors, logs, responses
- **D**enial of service: unbounded loops/memory, regex DoS
- **E**levation of privilege: sudo/root paths, trust boundary crossings

## Confidence gate

Score each finding 0–10. Only report findings ≥ 7/10.

- **< 7**: dismiss (false positive risk too high)
- **7–8**: MEDIUM
- **9+**: HIGH or CRITICAL

## Output format

```
## CSO Review

### Findings
#### Finding 1: {Name} — {CRITICAL|HIGH|MEDIUM} — confidence: {N}/10
**Category**: OWASP A{N} / STRIDE {letter}
**Where**: {file:line or function}
**Attack**: {specific attack scenario, step-by-step}
**Impact**: {what an attacker gains}
**Fix**: {concrete remediation}

### Summary
- CRITICAL: {n}
- HIGH: {n}
- MEDIUM: {n}

### Verdict: SECURE | VULNERABLE
```

**SECURE** = zero CRITICAL or HIGH findings with confidence ≥ 7.
**VULNERABLE** = any CRITICAL/HIGH finding at confidence ≥ 7.

## Not your job

Do NOT give "defensive programming" suggestions unless they fix a real vulnerability. This is not a code-style review. If the only findings are < 7/10 confidence, verdict is SECURE.

## Required MCP calls

| When | Tool |
|---|---|
| Before review | `agentboard_get_diff_stats(project_root)` — to see what you're reviewing |
| After verdict | `agentboard_checkpoint(project_root, run_id, "cso_complete", {secure: bool, findings_count, critical_count, high_count})` |
| After verdict | `agentboard_log_decision(project_root, task_id, iter=N, phase="cso", reasoning=<summary>, verdict_source="SECURE"\|"VULNERABLE")` |
| If findings worth remembering | `agentboard_save_learning(project_root, name, content, tags=["security", ...], category="pattern", confidence=0.8)` |

## On VULNERABLE

1. Call MCP tool `agentboard_log_decision(iter, phase='cso', reasoning=<summary>, verdict_source='VULNERABLE', ...)`
2. Hand back to `agentboard-tdd` with the finding — the implementation must be fixed and re-verified.
3. Do NOT approve PRs with CSO findings outstanding.

## On SECURE

1. Log decision with verdict_source='SECURE'
2. Hand off to `agentboard-redteam` (if enabled) or `agentboard-approval`
