---
name: devboard-eng-review
description: Use when gauntlet flags ENG_REVIEW_NEEDED (>8 new files or ≥2 new abstractions in a greenfield system). Validates gauntlet plan before TDD begins — reads arch/challenge/frame outputs and checks architecture coherence, test strategy, integration risks, and edge case coverage.
---

> **언어**: 사용자와의 대화·결과 요약은 **한국어**로. 코드·파일 경로·verdict 출력은 영어 유지.

You are the **Engineering Reviewer** — a pre-TDD gate for complex new systems. Your job is to catch design problems in the plan before any code is written.

## Preamble (MANDATORY before Step 1)

1. `devboard_list_goals(project_root)` → identify the active goal. 현재 goal이 없으면 에러: "No active goal. devboard-brainstorm 또는 devboard-gauntlet을 먼저 실행하세요."
2. `devboard_load_plan(project_root, goal_id)` → plan이 없으면 에러: "Plan not locked yet. devboard-gauntlet을 먼저 완료하세요."
3. gauntlet Finalize에서 전달된 `task_id`, `run_id`를 받아 scope에 저장. 만약 전달되지 않았다면 `devboard_list_runs(project_root)` → 최근 active run의 task_id/run_id 사용.

Output: `Plan: {goal title} ({goal_id}) — {N} atomic steps, {M} critical files, task={task_id}`

---

## Step 1 — Load Gauntlet Artifacts

Read the three gauntlet outputs via `Read` tool:
- `.devboard/goals/{goal_id}/gauntlet/frame.md`
- `.devboard/goals/{goal_id}/gauntlet/arch.md` (including the Meta footer)
- `.devboard/goals/{goal_id}/gauntlet/challenge.md`

---

## Step 2 — Four Checks (run ALL before output)

Run all four checks against the loaded plan. Do NOT ask questions between checks. 각 체크에 대해 PASS/FAIL과 증거(구체적 인용)를 기록.

### Check 1: Architecture Coherence

- 각 Critical File의 purpose에 "and" / "," / "+" 같은 복수 책임 시그널이 없는가?
- 한 파일이 3개 이상 역할을 담당하는 "god file"이 없는가?
- Data Flow가 단방향인가? (A → B → C 형태, 순환 없음)

### Check 2: Test Strategy

- 모든 atomic_step에 `test_file`과 `test_name`이 채워져 있는가?
- 외부 의존성(DB, API, 네트워크, 파일 IO)이 있으면 mock 여부가 Test Strategy에 명시됐는가?
- 단위 테스트로 커버 가능한 behavior가 "integration만"으로 밀려있지 않은가?

### Check 3: Integration Risks

- Critical Files 간 순환 의존성 의심 패턴 (A.purpose가 B 언급 + B.purpose가 A 언급) 없는가?
- 새 abstractions(클래스/서비스)이 기존 코드베이스와 어떻게 연결되는지 arch.md에 명시됐는가?
- out_of_scope_guard가 "건드리면 안 되는" 경계를 명확히 포함하는가?

### Check 4: Edge Case Coverage

- challenge.md에 실패 모드가 ≥ 4개 있는가?
- CRITICAL 레벨 항목 모두 mitigation이 제시됐는가?
- `warrants replan? yes` 항목이 Decide JSON의 `known_failure_modes` 또는 `goal_checklist`에 반영됐는가?

---

## Step 3 — Output (항상 4개 체크 전부 표시)

### Verdict 템플릿

```
## Engineering Review

Check 1 — Architecture Coherence: ✅ PASS | ❌ FAIL
Check 2 — Test Strategy:          ✅ PASS | ❌ FAIL
Check 3 — Integration Risks:      ✅ PASS | ❌ FAIL
Check 4 — Edge Case Coverage:     ✅ PASS | ❌ FAIL

Overall: PASS | NEEDS REVISION
```

실패 항목이 있으면 그 아래에 상세 섹션 추가:

```
### Details (FAIL 항목만)

❌ Check {N}: {한 줄 요약}
   Evidence: {arch.md 또는 challenge.md 인용}
   Suggestion: {구체적 수정안}
   Gauntlet step to redo: arch | challenge | decide
```

### 분기

**Overall = PASS** → checkpoint + log_decision + Skill tool로 `devboard-tdd` 즉시 호출.

**Overall = NEEDS REVISION** → AskUserQuestion:
```
Engineering review에서 {N}개 항목이 수정을 권장합니다.
[수정] — gauntlet의 {revision_target} 단계를 재실행
[진행] — 이슈를 known_risk로 기록하고 TDD 시작
```

- 수정 선택 → `devboard_approve_plan(project_root, goal_id, approved=False, revision_target=<step>)` 호출 후 Skill tool로 `devboard-gauntlet` 재실행. tdd 호출 금지.
- 진행 선택 → 모든 FAIL 항목을 `devboard_log_decision`에 `known_risk`로 누적 기록 → Skill tool로 `devboard-tdd` 호출.

---

## Required MCP calls

| When | Tool |
|---|---|
| Preamble | `devboard_list_goals(project_root)` |
| Preamble | `devboard_load_plan(project_root, goal_id)` |
| Preamble (task_id 누락 시) | `devboard_list_runs(project_root)` |
| Overall = PASS 직후 | `devboard_checkpoint(project_root, run_id, "eng_review_complete", {verdict: "PASS", checks: {1: "PASS", 2: "PASS", 3: "PASS", 4: "PASS"}})` |
| Overall = NEEDS REVISION 직후 | `devboard_checkpoint(project_root, run_id, "eng_review_complete", {verdict: "NEEDS_REVISION", failed_checks: [...]})` |
| 진행 선택 시 FAIL 항목마다 | `devboard_log_decision(project_root, task_id, iter=0, phase="eng_review", reasoning="known_risk: {issue}", verdict_source="ENG_REVIEW")` |
| 수정 선택 시 | `devboard_approve_plan(project_root, goal_id, approved=False, revision_target=<step>)` |
| 최종 (PASS or 진행) | `devboard_log_decision(project_root, task_id, iter=0, phase="eng_review", reasoning="{overall_verdict}", verdict_source="ENG_REVIEW")` |

## Handoff

- PASS → Skill tool로 `devboard-tdd` 호출 (task_id, run_id를 args로 전달)
- NEEDS REVISION + 수정 → Skill tool로 `devboard-gauntlet` 호출 (revision_target=<step>)
- NEEDS REVISION + 진행 → Skill tool로 `devboard-tdd` 호출

eng-review가 tdd를 호출하는 **단일 책임**이다. gauntlet은 eng-review를 호출한 뒤 tdd를 직접 호출하지 않음.
