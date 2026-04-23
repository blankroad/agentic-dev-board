---
name: agentboard-stress
description: D1d (2026-04-23). Pre-code adversarial review. Finds 4+ failure modes of the PLAN (not the code — that's agentboard-redteam after GREEN). Reads brainstorm.md + frame.md + arch.md YAML frontmatter. Distinct from agentboard-redteam (post-GREEN, targets code) — stress runs pre-code and targets design decisions. Not auto-invoked pre-cutover.
when_to_use: After agentboard-architecture completes (+ optional agentboard-eng-review if ENG_REVIEW_NEEDED=true). Auto-invoked by architecture at Step 12 handoff. Pre-cutover, invoke only when explicitly asked.
---

> **Language**: Respond to the user in Korean. This skill's instructions are in English; code, file paths, variable names, and commit messages remain English.

> **Status (2026-04-23, D1d CONTENT v1):** Ported from the legacy `agentboard-gauntlet` Step 4 Challenge with explicit boundary to post-GREEN `agentboard-redteam` + new `--deep=codex` spec. Parallel with the frozen gauntlet chain until D3 cutover.

You are the **Plan Red-Team** — Step 4 of the D1 phase chain. You argue against the plan, question edge-case coverage, probe scope drift vectors, and flag integration gaps. Your findings become `known_failure_modes` in the LockedPlan — they're the attack surface the code must survive.

## Boundary: stress vs redteam

Distinct skills with distinct timing:

| Skill | Timing | Target |
|---|---|---|
| `agentboard-stress` (YOU) | Pre-code, after architecture | Design decisions, assumptions, edge-case coverage of the PLAN |
| `agentboard-redteam` | Post-GREEN, after implementation | Concrete code behavior — can you break the actual tests / running system? |

Example: at stress time you'd argue "the plan's test strategy doesn't cover concurrent access to the alias file." At redteam time you'd actually trigger the race and show it breaks.

**If you find yourself trying to run the code or grep tests — STOP.** That's redteam territory. You work from the phase artifacts only.

## Step 0 — Preamble (project guard + upstream load)

### Project guard (MANDATORY first check)

```bash
test -d .devboard && test -f .mcp.json && echo OK || echo MISSING
```

### Load upstream

Read and parse YAML frontmatter:

- `.devboard/goals/<goal_id>/brainstorm.md` — `scope_mode`, `refined_goal`, `alternatives_considered` (chosen)
- `.devboard/goals/<goal_id>/gauntlet/frame.md` — `riskiest_assumption`, `key_assumptions`, `non_goals`, `success_definition`
- `.devboard/goals/<goal_id>/gauntlet/arch.md` — `critical_files`, `edge_cases`, `test_strategy`, `critical_path`, `out_of_scope_guard`, `design_review` section if `ui_surface=true`

If `arch.md` contains a `## Design Review` section with WARN items, those are explicit hints — expand on them adversarially as failure modes.

---

## Step 1 — Generate failure modes (minimum 4, distinct categories)

Produce at least 4 failure modes. Each must be:

- **Specific** — names a concrete input, condition, or path (not "something might go wrong")
- **Rooted in upstream evidence** — cites a field from frame/arch, or attacks the `riskiest_assumption`
- **Testable as a prediction** — if you wrote the failure mode today, you could verify/refute after code lands

### Required coverage (span these 5 categories, minimum 4 failure modes)

1. **Scope drift risks** — where does the plan tempt the implementor to do more than committed? E.g. "Critical File X's purpose says 'emit YAML' but touches the validation layer; drift into validating inputs expands scope."
2. **Architectural flaws** — does the data flow actually deliver `critical_path`? E.g. "Arch says A calls B, but B's input shape doesn't match A's output — integration will fail."
3. **Missing edge cases** — `frame.riskiest_assumption` should be an edge case, but isn't in `arch.edge_cases` → FLAG.
4. **Integration gaps** — touches outside `critical_files` that aren't accounted for. E.g. "`file_store.py` is modified but `storage/base.py` protocol isn't updated → type mismatch on call sites."
5. **Test coverage gaps** — `must_test` doesn't cover the `critical_path` OR doesn't exercise the `riskiest_assumption` probe.

### For each failure mode

Format:

```markdown
## Failure Mode N — {NAME}  ({SEVERITY})

**Why it fails**: <root cause tied to arch.md / frame.md citation>
**Concrete trigger**: <input / condition that produces the failure>
**Mitigation**: <specific code-level fix or plan-level change>
**Warrants replan?**: YES | NO
```

Severity rubric:

- **CRITICAL** — plan cannot ship with this unresolved. `Warrants replan` defaults YES.
- **HIGH** — ships but fragile; write a test that covers it before merging.
- **MEDIUM** — fix opportunistically; document in `known_failure_modes`.

---

## Step 2 — Self-audit the failure modes

Before writing `challenge.md`, review your own output:

1. **Distinctness** — no two failure modes attack the same root. Merge duplicates; the count still needs ≥4 distinct.
2. **Citations** — every failure mode references a specific field from `frame.md` or `arch.md` (file + field name). "Generic adversarial thoughts" are not enough.
3. **Mitigations are concrete** — avoid "add more tests" (vague). "Add `test_save_brainstorm_rejects_non_dict_alternatives` asserting ValueError on non-dict items" (concrete).
4. **Riskiest assumption probed** — `frame.riskiest_assumption` shows up in at least one failure mode. If not, force-add.
5. **`warrants_replan`** — if any CRITICAL has `Warrants replan: YES`, set frontmatter `warrants_replan: true`.

If any check fails: regenerate that failure mode once. Retry cap: 1.

---

## Step 3 — Write challenge.md

Write `.devboard/goals/<goal_id>/gauntlet/challenge.md`:

```yaml
---
phase: stress
status: completed
inputs:
  - brainstorm.md
  - frame.md
  - arch.md
failure_modes_count: <int, ≥4>
critical_count: <int>
high_count: <int>
medium_count: <int>
warrants_replan: <bool>
riskiest_assumption_probed: <bool>
---

## Failure Mode 1 — {NAME}  ({CRITICAL | HIGH | MEDIUM})

**Why it fails**: ...
**Concrete trigger**: ...
**Mitigation**: ...
**Warrants replan?**: YES | NO

## Failure Mode 2 — ...

...

## Summary

### CRITICAL issues
- <name 1>
- <name 2>

### HIGH issues
- <name>

### MEDIUM issues
- <name>
```

---

## Step 4 — Self-review sentinel

```
agentboard_log_decision(
  phase="self_review",
  reasoning="<Distinctness / Citations / Concrete Mitigations / Riskiest Probed verdicts>",
  verdict_source="PASSED" | "WARNING",
)
```

---

## Step 5 — Handoff to lock

After `challenge.md` written:

1. `agentboard_log_decision(phase="stress", verdict_source="COMPLETED", reasoning="<CRITICAL/HIGH/MEDIUM counts + warrants_replan verdict>")`.
2. Branch on `warrants_replan`:
   - **false** → output summary + invoke `agentboard-lock` via the `Skill` tool.
   - **true** → `AskUserQuestion`:

     ```
     CRITICAL 실패 모드 중 replan 권고가 있습니다:
       {CRITICAL name 1 one-liner}

     다음 중 선택:
     (1) architecture 재작성 (back to agentboard-architecture)
     (2) frame 재작성 (back to agentboard-frame)
     (3) intent 재작성 — scope_mode 자체가 틀림 (back to agentboard-intent)
     (4) 그대로 lock 진행 — known_failure_modes에 기록하고 코드 단계에서 해결
     ```

   Route per user pick. Options (1)-(3) exit and invoke the named upstream skill. Option (4) proceeds to lock but logs `verdict_source="REPLAN_DECLINED"`.

3. Output:

   ```
   ## Stress 완료

   저장: .devboard/goals/{goal_id}/gauntlet/challenge.md
   CRITICAL: {N} / HIGH: {N} / MEDIUM: {N}
   warrants_replan: {bool}

   agentboard-lock을 시작합니다.  (or: agentboard-<upstream> 재작성)
   ```

**Do NOT invoke `agentboard-gauntlet`** — legacy chain frozen.

---

## `--deep` modes (gstack wrapper)

### `--deep=codex` — 200 IQ second opinion via gstack `codex` skill

**Trigger**: user writes "stress --deep=codex", "codex challenge this", "second opinion", or an earlier phase flagged high risk (e.g., `frame.riskiest_assumption` mentions concurrency / crypto / protocol edge cases).

**Flow**:

1. Run Step 1 AS NORMAL — produce your own 4+ failure modes first. Codex is a second opinion, not a replacement.
2. Invoke the gstack skill via the `Skill` tool in `challenge` mode:

   ```
   Skill(skill="codex", args=f"""
   mode: challenge

   <context>
   goal_id: {goal_id}
   brainstorm.md frontmatter: {brainstorm_yaml}
   frame.md (full): {frame_full}
   arch.md (full): {arch_full}
   stress draft (your own failure modes from Step 1): {stress_draft}
   </context>

   Run adversarial challenge on the PLAN (not the code — no code exists yet).
   Produce 4+ additional failure modes with Codex's 200 IQ perspective.
   Each finding: severity (CRITICAL/HIGH/MEDIUM), root cause, concrete trigger,
   mitigation, warrants_replan verdict.

   Specifically stress-test:
   - The riskiest_assumption from frame.md
   - The critical_path from arch.md
   - Edge cases the stress draft may have missed
   - Integration boundaries against out_of_scope_guard

   Return structured findings. Do NOT write to decisions.jsonl — the parent
   agentboard-stress will aggregate and log once.
   """)
   ```

3. Parse Codex's response into Finding objects with `category_namespace="codex"`.
4. Dedupe against your own findings — if Codex's finding + your finding share root + trigger, keep the higher-severity one and merge rationales. Otherwise append Codex's as a new entry.
5. Tag Codex findings in challenge.md body as `[codex]` suffix on the `## Failure Mode N` heading for traceability:

   ```markdown
   ## Failure Mode 5 — {NAME}  ({SEVERITY}) [codex]

   **Why it fails**: ...
   ```

6. Re-run Step 2 Self-audit on the COMBINED set. Count triggers (`failure_modes_count` in frontmatter) includes the merged total.

**Fold-back contract**: on Codex timeout / error / empty response, log `verdict_source="DEEP_CODEX_INCOMPLETE"` and proceed with your own findings only. Challenge.md still ships with ≥4 failure modes from Step 1.

**Token discipline**: Codex dispatch has real latency and token cost. Skip `--deep=codex` on goals where your own Step 1 findings already include ≥6 well-cited distinct failure modes covering all 5 required categories — Codex's ROI drops sharply at that point.

### Invariants across `--deep`

- Minimum 4 distinct failure modes still required (yours alone, OR the merged set when `--deep=codex` succeeds).
- `warrants_replan` computed over the UNION of your + Codex's findings.
- `challenge.md` structure unchanged (same sections, same frontmatter schema).
- Self-audit (Step 2) runs AFTER merge, not before.
- `category_namespace="codex"` on all Codex-originated findings so retro can distinguish who found what.
- Exactly one `--deep` flag per invocation. (Codex is currently the only depth mode for stress; future additions would follow the same wrapper pattern.)

---

## Required MCP calls

| When | Tool |
|---|---|
| Step 0 — upstream load | (direct `Read` on brainstorm / frame / arch .md files) |
| Step 4 — self-review sentinel | `agentboard_log_decision(phase="self_review", ...)` |
| Step 5 — completion | `agentboard_log_decision(phase="stress", verdict_source="COMPLETED", ...)` |
| Step 5 — replan routing | `AskUserQuestion` + `Skill(agentboard-<upstream>, ...)` |
| Step 5 — normal handoff | `Skill(agentboard-lock, ...)` |
| `--deep=codex` | `Bash` invocation of Codex CLI (exact interface TBD) |

`challenge.md` written directly — no MCP wrapper yet.

---

## Design notes (why this structure)

- **Pre-code only.** The post-code adversarial lives in `agentboard-redteam`. Mixing the two blurs when the attack applies — is the plan broken or is the code broken? — and makes remediation routing ambiguous. Keep them separate.
- **4 is the floor, not the ceiling.** Too few findings and the skill isn't paying for itself. More than 8 usually means some are duplicates or speculation — audit.
- **Citations mandatory.** Generic "this might break in production" is not adversarial; it's noise. A finding without a `arch.md#<field>` or `frame.md#<field>` citation is a red flag for the self-audit.
- **Riskiest assumption probe is REQUIRED coverage.** Frame surfaces it, arch edge-cases should include it, but it's easy to let slip. Stress is the last gate before lock — if the riskiest assumption isn't adversarially tested here, it's unlikely to be caught later.
- **`warrants_replan` routes back to the correct upstream.** Asking the user `(1) arch (2) frame (3) intent (4) proceed` gives them explicit agency over the rollback depth. F4 lesson: don't silently loop on the same phase.
- **`--deep=codex` is opt-in.** Codex dispatch has latency and token cost; save for heavy plans.

---

## Freeze notice

Default skill routing still runs the legacy gauntlet. This skill executes only when explicitly invoked OR when upstream `agentboard-architecture` hands off. See `memory/feedback_freeze_gauntlet_flow.md`.
