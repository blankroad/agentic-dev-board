# devboard

> **자율형 에이전틱 터미널 Dev Board**
> 하이레벨 목표 하나 → Planning Gauntlet으로 의도 락인 → TDD 루프로 수렴 → 승인 후 PR.
> 전 과정의 `what`(코드 이력)과 `why`(의도 이력)를 둘 다 완전 보존.

<p align="center">
  <img alt="tests" src="https://img.shields.io/badge/tests-190%20passed-brightgreen" />
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-blue" />
  <img alt="model" src="https://img.shields.io/badge/model-claude--opus--4.7%20%7C%20sonnet--4.6-purple" />
  <img alt="stack" src="https://img.shields.io/badge/stack-typer%20%7C%20textual%20%7C%20langgraph-lightgrey" />
</p>

---

## TL;DR

```bash
# 1회 셋업
pip install -e .
export ANTHROPIC_API_KEY=sk-...
devboard init

# 목표 추가 → 5단계 Gauntlet으로 락인
devboard goal add "Build calculator.py with add/sub/mul/div and ZeroDivisionError on div(x, 0). Include pytest suite."
devboard goal plan <goal_id>

# 자율 루프 (TDD + verify + security + red-team 전부 활성)
devboard run --goal <goal_id> --redteam

# 수렴 후 승인 → push + PR
devboard approve <task_id>

# 언제든 TUI 보드
devboard board
```

---

## 철학 6기둥

| # | 원칙 | 의미 |
|---|---|---|
| 1 | **Honest over hopeful** | 불확실성 과보고, 실패 은폐 금지. "should work" 없음 |
| 2 | **Decisions are first-class artifacts** | *why* 는 조회 가능한 객체. 모든 phase 결정이 `decisions.jsonl`에 남음 |
| 3 | **The loop is the product** | 품질은 반복·red-team·reflection에서 나온다 |
| 4 | **Human as orchestrator** | 승인자가 아닌 **방향 전환자**. `Ctrl+I`로 mid-flight hint |
| 5 | **Time-reversible** | 어느 체크포인트든 replay·분기. 복구 가능 |
| 6 | **Local trust, remote ceremony** | 로컬 자유, 네트워크 경계는 엄격. Push는 2차 승인 후 |

Superpowers의 **Iron Law of TDD**(실패 테스트 없이 production code 금지), **Evidence over claims**, **Systematic debugging**이 이 위에 얹혀 있다.

---

## 3단계 게이트 플로우

```
┌───────────────────────────────────────────────────────────────────────┐
│  0차 — Planning Gauntlet           (goal → LockedPlan, 5 steps)       │
│    Frame → Scope → Architecture → Challenge → Decide                  │
│    산출물: .devboard/goals/<id>/plan.md + atomic_steps + token_ceiling│
└────────────────┬──────────────────────────────────────────────────────┘
                 │ (locked_hash SHA256)
                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  1차 — Autonomous TDD Loop         (LangGraph cyclic state machine)   │
│                                                                       │
│    plan → tdd_red → tdd_green → tdd_refactor → verify → review        │
│                                    ↓                      ↓           │
│                             (fresh pytest,            (PASS)          │
│                              no LLM)                   ↓              │
│                                                  cso ─► redteam       │
│                                                   ↓        ↓          │
│                                                 (SECURE + SURVIVED)   │
│                                                      ↓                │
│                                                  commit ──► 다음 iter │
│                                    ↑                                  │
│    reflect (4-phase RCA) ──────────┘ (on RETRY)                       │
│      + 3회 연속 실패 = Escalate to Gauntlet rerun                     │
│                                                                       │
│  각 반복: local git commit, iter_N.diff, decisions.jsonl append       │
└────────────────┬──────────────────────────────────────────────────────┘
                 │ converged=True  (verdict=PASS ∧ tests green
                 │                  ∧ checklist 모두 ✓ ∧ no further diff)
                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  2차 — Approval Gate               (devboard approve <task_id>)       │
│    diff stats + checklist + key decisions 요약 제시                   │
│    Squash policy 선택: squash | semantic | preserve | interactive     │
│    사용자 승인 → git push + gh pr create (본문에 gauntlet 요약 자동)  │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 아키텍처 전개도

```
┌──────────────────────────────────────────────────────────────┐
│  Typer CLI:                                                  │
│   init | goal | run | board | approve | replay | rethink     │
│   retro | audit | learnings                                  │
└───────┬───────────────────────────────────────────────┬──────┘
        │                                               │
   ┌────▼─────┐                                   ┌─────▼──────┐
   │  TUI     │◄───────── BoardState ─────────────┤Orchestrator│
   │ Textual  │                                   │ LangGraph  │
   └──────────┘                                   └─────┬──────┘
                                                        │
           ┌────────────────────────────────────────────┤
           ▼                                            ▼
┌────────────────────────┐              ┌──────────────────────────┐
│ Gauntlet (Phase 0)     │              │ TDD Loop (Phase 1)       │
│  Frame    (Sonnet)     │  locked      │  Planner    (Opus+think) │
│  Scope    (Opus+think) │  plan ──►    │  TDD R/G/R  (Sonnet)     │
│  Arch     (Opus+think) │              │  Verify     (deterministic)│
│  Challenge(Opus)       │              │  Reviewer   (Opus+think) │
│  Decide   (Sonnet)     │              │  CSO        (Opus+think) │
└────────────────────────┘              │  Red-team   (Opus)       │
                                        │  Reflect/RCA(Sonnet)     │
                                        └─────────┬────────────────┘
                                                  │
                              ┌───────────────────┼──────────────┐
                              ▼                   ▼              ▼
                           ┌─────┐            ┌──────┐       ┌─────┐
                           │ FS  │            │Shell │       │ Git │
                           │scoped│           │allow-│       │local│
                           │touches│          │list+ │       │only │
                           │forbids│          │careful│      │     │
                           └─────┘            └──────┘       └─────┘

   ┌─────────────────────────────────────────────────────────┐
   │ Storage                                                  │
   │  .devboard/                                              │
   │    config.yaml  state.json                               │
   │    goals/<id>/                                           │
   │      plan.md  gauntlet/{frame,scope,arch,challenge,decide}.md │
   │      tasks/<id>/                                         │
   │        task.md  changes/iter_N.diff  decisions.jsonl     │
   │    learnings/*.md   (frontmatter: tags, category, confidence) │
   │    runs/<run_id>.jsonl   (every state transition)        │
   │    retros/retro_<ts>.md                                  │
   └─────────────────────────────────────────────────────────┘
```

---

## 설치

```bash
git clone <repo> cli-dev-board
cd cli-dev-board
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export ANTHROPIC_API_KEY=sk-...
devboard --help
```

**요구사항**: Python 3.11+, `git`, `pytest` (verify 노드용), 선택적으로 `gh`(PR 생성용).

---

## 빠른 시작 (End-to-End)

```bash
# 프로젝트 초기화
cd my-project
devboard init
#   ✓ Initialized devboard at /path/to/my-project
#     Board ID: b_20260417_...

# 복잡한 목표 추가 — 의도적으로 첫 시도 실패를 유발해 루프 검증 가능
devboard goal add "Add calculator.py with add/sub/mul/div functions. \
div(a, 0) must raise ZeroDivisionError. Include pytest tests for all cases."

# Planning Gauntlet 실행 (5단계 LLM 호출, 해시 락인)
devboard goal plan g_20260417_...
#   Step 1/5: Frame...   ✓
#   Step 2/5: Scope...   ✓  [HOLD]
#   Step 3/5: Arch...    ✓
#   Step 4/5: Challenge...✓  [2 CRITICAL, 1 HIGH]
#   Step 5/5: Decide...  ✓
#   ✓ Locked plan saved — .devboard/goals/g_.../plan.md
#   Checklist: 3 items, Atomic steps: 4

# 자율 TDD 루프 시작 (red-team + CSO 자동 활성)
devboard run --goal g_20260417_... --redteam
#   ── Iteration 1/5 ──
#     Planning...       ✓
#     RED step=s_001 — add(1,2)==3
#       → RED_CONFIRMED
#     GREEN step=s_001
#       → GREEN_CONFIRMED
#     REFACTOR step=s_001
#       → SKIPPED
#     Verifying (fresh evidence)...
#       ✓ Verify suite=PASS  items=1/3
#   ── Iteration 2/5 ──
#     (repeat for s_002, s_003, s_004)
#   ...
#   ── Iteration 4/5 ──
#     Reviewing...      Reviewer: PASS
#     Red-team attack... SURVIVED
#   ✓ Converged at iteration 4  48,230 tokens | $0.0321

# 승인 게이트 — diff + decisions 요약 + squash 정책 선택
devboard approve t_...
#   Iterations completed: 4
#   Goal Checklist:
#     ✓ calculator.py with add/sub/mul/div
#     ✓ div raises ZeroDivisionError
#     ✓ pytest suite passes
#   Squash policy: 1) squash  2) semantic  3) preserve  4) interactive
#   Choice [1]: 1
#   Approve and push? [y/N]: y
#   ✓ PR created: https://github.com/user/my-project/pull/42

# 언제든 TUI로 보드 확인
devboard board     # F1: Board  F2: Log  Ctrl+I: hint  Ctrl+Q: quit

# 레트로 리포트
devboard retro --last-n 5 --save
```

---

## 핵심 개념

### 1. **Locked Plan** (의도의 SHA256 해시)

Gauntlet 5단계 결과는 하나의 `LockedPlan` 객체로 압축되어 `.devboard/goals/<id>/plan.md`에 저장된다:

```yaml
---
goal_id: g_20260417_...
locked_at: 2026-04-17T...
locked_hash: 5a41a79b2124b75e      # 변경 감지용 SHA256[:16]
---
problem: ...
non_goals: [...]
scope_decision: HOLD
architecture: ...
known_failure_modes: [CRITICAL: ..., HIGH: ...]
goal_checklist:
  - calculator.py with 4 functions
  - div raises ZeroDivisionError
  - pytest passes
out_of_scope_guard:
  - src/payments/
  - src/auth/
atomic_steps:
  - id: s_001
    behavior: add(1,2)==3
    test_file: tests/test_calc.py
    test_name: test_add_two_positives
    impl_file: calculator.py
    expected_fail_reason: "NameError: add not defined"
  - ...
token_ceiling: 200000
max_iterations: 5
```

**불변식**:
- 모든 Reviewer 판정은 `goal_checklist`에 대해 이뤄짐. "테스트 통과"만으로는 PASS 불가
- Executor가 `out_of_scope_guard` path를 touch하면 FS tool이 거부
- Locked plan 수정이 필요하면 `devboard rethink` 재실행 (사용자 재승인)

### 2. **TDD 루프 (Red-Green-Refactor)**

`atomic_steps`가 있으면 TDD 경로 활성:

```
RED     → 한 step의 failing test 작성, pytest 실행해 빨강 확인
GREEN   → 최소 production 코드로 초록 만들기 (YAGNI)
REFACTOR → 중복/네이밍 정리 (테스트 변경 금지, skip 가능)
VERIFY  → 결정론적 pytest 실행, VerificationReport 생성 (LLM 없음)
```

**Iron Law of TDD**: 실패 테스트 없이 production code 작성 금지. `agents/iron_law.py`가 tool_call 시퀀스를 감시해서 위반하면 경고(`--strict-tdd`면 halt).

### 3. **다층 리뷰 스택**

```
Reviewer (기본)
   → CSO       (diff에 auth/sql/subprocess 등 보안 키워드 있을 때만)
   → Red-team  (--redteam 플래그, 적대적 QA 페르소나)
   → commit
```

| 리뷰어 | 역할 | 차단 조건 |
|---|---|---|
| Reviewer | goal_checklist vs evidence | RETRY/REPLAN 판정 |
| CSO | OWASP Top 10 + STRIDE | VULNERABLE (confidence ≥ 7/10) |
| Red-team | 깨는 시나리오 3+ 찾기 | BROKEN verdict |

어느 하나라도 fail → RETRY로 downgrade → reflect → 다음 iteration.

### 4. **Systematic Debugging (4-phase RCA)**

Reflect 노드는 단순 "뭐가 틀렸지?"가 아니라:

```
Phase 1 Investigate  → 에러/스택/데이터 flow 역추적
Phase 2 Pattern      → 잘 동작하는 유사 코드 찾아 차이점 열거
Phase 3 Hypothesis   → "X가 근본 원인 because Y" — ONE 가설
Phase 4 Fix          → regression test 먼저, 다음 최소 수정
```

동일 증상 3회 연속 실패 → `escalate=True` → 루프 halt → `devboard rethink` 유도.

### 5. **2-Track Git 이력**

| Track | 위치 | 정책 |
|---|---|---|
| **Process** (감사) | `.devboard/tasks/<id>/changes/iter_N.diff` + `decisions.jsonl` | 무손실, squash와 무관 |
| **Code** (서사) | `devboard/<goal>/<task>` 로컬 브랜치 | iter마다 로컬 commit (aggressive), push 전 정리 |

**Push 시점에 정리 정책 선택**: squash (default, PR 본문에 decisions 요약) / semantic / preserve (감사 환경) / interactive.

### 6. **Time-travel Replay**

모든 state 전이가 `.devboard/runs/<run_id>.jsonl`에 체크포인트됨.

```bash
devboard replay <run_id> --from 2 --variant "try async instead"
# iter 2 시점의 state에서 분기 → 새 run_id로 실행
# 새 run도 독립적으로 체크포인트됨
```

---

## CLI 명령 레퍼런스

### 목표 관리

| 명령 | 설명 |
|---|---|
| `devboard init [PATH]` | `.devboard/` 스캐폴드 + `.gitignore` 업데이트 |
| `devboard goal add "<desc>"` | 목표 추가. 첫 목표는 자동으로 active |
| `devboard goal list` | Kanban 스타일 테이블 출력 |
| `devboard goal plan <id>` | Planning Gauntlet 실행 (5-step) |
| `devboard rethink <id>` | 기존 plan 폐기 후 Gauntlet 재실행 |

### 실행

| 명령 | 플래그 | 설명 |
|---|---|---|
| `devboard run` | `--goal ID` | 자율 TDD 루프. plan 없으면 gauntlet 자동 실행 |
| | `--no-tdd` | TDD 비활성, 레거시 single-shot executor |
| | `--strict-tdd` | Iron Law 위반 시 즉시 halt |
| | `--redteam` | 적대적 reviewer 활성 |
| | `--no-cso` | 보안 리뷰어 비활성 (민감 diff도 skip) |
| | `--dry-run` | 계획만 표시, 실행 안 함 |
| `devboard replay <run_id>` | `--from N --variant "..."` | iter N에서 분기 재실행 |

### 승인 & PR

| 명령 | 플래그 | 설명 |
|---|---|---|
| `devboard approve <task_id>` | `--policy squash\|semantic\|preserve\|interactive` | 2차 승인 게이트 → push + `gh pr create` |
| | `--base BRANCH` | PR base (default `main`) |
| | `--draft` | Draft PR |
| | `--dry-run` | 실제 push 없이 시뮬레이션 |

### 관찰성

| 명령 | 설명 |
|---|---|
| `devboard board` | Textual TUI. F1=Board, F2=Log, Ctrl+R=refresh, Ctrl+I=hint inject |
| `devboard task show <id>` | 특정 task 상세 (iteration 블록, verdict 등) |
| `devboard retro [--goal ID\|--last-n N] [--save]` | 목표별/전체 레트로 리포트 |
| `devboard audit` | Self-DX 체크 — 커맨드 help 누락, API key, git/pytest/gh 버전 |

### 지식 관리

| 명령 | 설명 |
|---|---|
| `devboard learnings list` | 모든 learning (confidence 내림차순) |
| `devboard learnings search [QUERY] [--tag T] [--category C]` | 태그 + 카테고리 + 본문 검색 |

### 설정

| 명령 | 예 |
|---|---|
| `devboard config KEY VALUE` | `devboard config tdd.enabled false` |

---

## 설정 (`.devboard/config.yaml`)

```yaml
max_iterations: 10
token_ceiling: 500000
git_push_policy: squash    # squash | semantic | preserve | interactive
dry_run: false

llm:
  planner_model: claude-opus-4-7
  executor_model: claude-sonnet-4-6
  reviewer_model: claude-opus-4-7
  gauntlet_model: claude-opus-4-7
  haiku_model: claude-haiku-4-5-20251001
  max_tokens: 8192
  thinking_budget: 5000

tools:
  shell_allowlist: [python, pytest, pip, git, gh, ls, cat, ...]
  shell_timeout: 60
  sandbox_enabled: false

tdd:
  enabled: true                # Red-Green-Refactor 루프
  strict: false                # True면 Iron Law 위반시 halt
  verify_with_evidence: true   # 결정론적 verify_node 활성
  systematic_debug: true       # 4-phase RCA
  require_atomic_steps: false
  allow_refactor_skip: true    # REFACTOR skip 허용 (기본)
```

**Cost-aware routing**: budget 70% 소진 → Opus → Sonnet. 90% 소진 → 전부 Haiku.

---

## Storage Layout

```
.devboard/
├── config.yaml
├── state.json                     # 보드 인덱스 (goals, active_goal)
├── goals/
│   └── <goal_id>/
│       ├── plan.md                # LockedPlan (frontmatter + body)
│       ├── plan.json              # 기계 가독 사본
│       ├── gauntlet/
│       │   ├── frame.md
│       │   ├── scope.md
│       │   ├── arch.md
│       │   ├── challenge.md
│       │   └── decide.md
│       └── tasks/
│           └── <task_id>/
│               ├── task.md        # iteration 블록 append-only
│               ├── task.json
│               ├── changes/
│               │   ├── iter_1.diff
│               │   └── iter_2.diff
│               └── decisions.jsonl   # append-only "why" 이력
├── learnings/
│   └── <name>.md                  # frontmatter: tags, category, confidence, source
├── runs/
│   └── <run_id>.jsonl             # LangGraph 체크포인트
└── retros/
    └── retro_<timestamp>.md
```

`.gitignore`에 `.devboard/runs/`, `.devboard/state.json`, `.devboard/goals/` 추가됨 (init 시 자동).

---

## 안전 장치

| 계층 | 메커니즘 |
|---|---|
| **FS scoped permissions** | `touches` allowlist + `forbids`(out_of_scope_guard) blocklist. 경로 탈출 시도 거부 |
| **Shell allowlist** | 기본 허용: python/pytest/git/gh/ls/cat 등. 명령어 단위 |
| **DangerGuard** | `rm -rf /`, fork bomb, `dd of=/dev/*` → 하드 블록. `git push --force`, `DROP TABLE`, `curl \| sh` → warn |
| **Iron Law detector** | tool_call 시퀀스 감시 — 테스트 없이 production code 작성 감지 |
| **Locked plan hash** | plan 파일 변조 감지 |
| **외부 경계** | git push / gh PR / Jira write는 `approve` 게이트 이후만 |
| **Token budget** | goal별 ceiling 초과 시 loop halt |
| **Max iterations** | 기본 10 (gauntlet이 2-10 범위에서 결정) |
| **Never force-push** | 설계적으로 금지. `git reset --hard` 같은 파괴적 명령은 DangerGuard가 warn |

---

## 내부 구조

```
src/devboard/
├── cli.py                          # Typer entry point (13 commands)
├── config.py                       # DevBoardConfig, LLMConfig, TDDConfig, ToolConfig
├── models.py                       # Pydantic: Goal, Task, LockedPlan, AtomicStep, DecisionEntry
├── gauntlet/
│   ├── pipeline.py                 # run_gauntlet() - 5-step sequential
│   ├── lock.py                     # build_locked_plan() + SHA256 hashing
│   └── steps/
│       ├── frame.py scope.py arch.py challenge.py decide.py
│       └── brainstorm.py           # Socratic gate (Phase G)
├── orchestrator/
│   ├── graph.py                    # LangGraph StateGraph (TDD path + legacy path)
│   ├── runner.py                   # run_loop() - compiles + invokes graph
│   ├── state.py                    # LoopState, IterationRecord
│   ├── checkpointer.py             # JSONL append-only
│   ├── verify.py                   # Deterministic pytest runner → VerificationReport
│   ├── interrupt.py                # HintQueue (HITL)
│   ├── approval.py                 # PR body builder + squash policy
│   └── push.py                     # git push + gh pr create
├── agents/
│   ├── base.py                     # run_agent() - agentic tool-use loop
│   ├── planner.py executor.py      # 레거시 경로
│   ├── reviewer.py                 # PASS/RETRY/REPLAN
│   ├── cso.py                      # OWASP + STRIDE (Phase H)
│   ├── redteam.py                  # 적대적 QA
│   ├── reflect.py                  # 간단한 reflect (fallback)
│   ├── systematic_debug.py         # 4-phase RCA (Phase G default)
│   ├── tdd.py                      # run_tdd_red/green/refactor (Phase G)
│   ├── iron_law.py                 # Iron Law 위반 감지 (Phase G)
│   └── router.py                   # Cost-aware model tier routing
├── tools/
│   ├── base.py                     # ToolDef, ToolRegistry
│   ├── fs.py                       # scoped fs_read/write/list
│   ├── shell.py                    # allowlisted + DangerGuard
│   ├── git.py                      # branch/commit/diff (no push)
│   └── careful.py                  # destructive pattern detector (Phase H)
├── storage/
│   ├── base.py                     # Repository protocol
│   ├── file_store.py               # JSON + Markdown round-trip
│   └── jira_store.py               # stub (Phase E)
├── memory/
│   ├── learnings.py                # frontmatter-based learnings (Phase H)
│   └── retriever.py                # keyword + tag + confidence scoring
├── replay/
│   └── replay.py                   # time-travel branching
├── analytics/
│   └── retro.py                    # Retrospective report (Phase H)
├── llm/
│   ├── client.py                   # Anthropic wrapper + prompt caching
│   ├── budget.py                   # BudgetTracker (cost estimate)
│   └── prompts/
│       ├── gauntlet/
│       │   ├── frame.md scope.md arch.md challenge.md decide.md
│       │   └── brainstorm.md       # Phase G
│       └── loop/
│           ├── planner.md executor.md reviewer.md reflect.md
│           ├── redteam.md cso.md                # Phase F/H
│           ├── tdd_red.md tdd_green.md tdd_refactor.md  # Phase G
│           └── systematic_debug.md              # Phase G
└── tui/
    ├── app.py                      # DevBoardApp (Textual)
    ├── board_view.py               # DataTable of goals
    ├── gauntlet_view.py            # 5-step progress indicator
    ├── task_view.py                # Checklist + iteration table
    └── log_view.py                 # Live RichLog
```

**총 61 Python 모듈 + 16 프롬프트 템플릿**.

---

## 개발 빌드된 Phase

| Phase | 범위 | 상태 |
|---|---|---|
| **A — Foundations** | Typer CLI, Pydantic 모델, FileStore, config | ✓ |
| **A2 — Planning Gauntlet** | 5-step pipeline, LockedPlan, borderline decisions | ✓ |
| **B — Agents** | Planner/Executor/Reviewer + fs/shell/git tools, linear loop | ✓ |
| **C — LangGraph Cyclic Loop** | Reflect, 수렴 체크, JSONL checkpointer, per-iter commits | ✓ |
| **D1 — TUI** | Textual board, gauntlet view, log stream | ✓ |
| **D2 — Approval + Push** | Squash 정책, `gh pr create`, PR body 자동 생성 | ✓ |
| **E — Sync adapters** | Jira/Linear stubs | ⚠ stub only |
| **F — Maturity (Tier 1+2)** | Red-team, Learnings v1, HITL, Replay, cost routing, scoped perms | ✓ |
| **G — TDD Discipline** | R-G-R cycle, verify (deterministic), 4-phase RCA, Iron Law, brainstorm | ✓ |
| **H — Multi-perspective Review** | CSO (OWASP+STRIDE), DangerGuard, Retro, Learnings v2, self-audit | ✓ |

---

## 테스트

```bash
.venv/bin/pytest -v                 # 190 passed
.venv/bin/pytest tests/test_phase_g.py -v   # TDD 루프 테스트만
.venv/bin/pytest tests/test_phase_h.py -v   # CSO + DangerGuard + retro
```

**커버리지 영역**:
- `test_file_store.py` (14): storage round-trip
- `test_gauntlet.py` (8): 5-step pipeline + locking
- `test_graph.py` (12): LangGraph cyclic state machine
- `test_agents.py` (8): agentic loop + tool extraction
- `test_tools.py` (14): FS scope, shell allowlist
- `test_tui.py` (5): Textual pilot
- `test_approval.py` (14): PR body, squash policy, push
- `test_phase_f.py` (28): red-team, learnings, hint queue, replay, cost router, scoped fs
- `test_phase_g.py` (40): TDD R/G/R, verify, 4-phase RCA, brainstorm, iron law
- `test_phase_h.py` (47): DangerGuard, learnings v2, retro, CSO

---

## 디자인 결정 근거

### 왜 LangGraph?
단순 for-loop이 아니라 **그래프**여야 하는 이유: state 전이가 조건적이고(PASS/RETRY/REPLAN에 따라 경로가 다름), 시간 여행이 필요하며(체크포인트 resume/branch), 노드 하나를 통째로 교체 가능해야 하기 때문. LangGraph의 `StateGraph + conditional_edges`가 정확히 이 모양.

### 왜 결정론적 verify_node?
Evidence-over-claims 원칙. LLM이 "tests should pass" 라고 말하는 것과 실제 pytest exit code가 0인 것은 다르다. verify는 LLM 없이 실제 커맨드 실행 결과만 본다.

### 왜 `.devboard/` 2-track?
Git squash 이후에도 "왜 그 결정을 내렸는가"는 남아야 한다. decisions.jsonl은 append-only, git과 무관하게 항상 완전. PR 본문은 이걸 요약해서 생성한다.

### 왜 CSO를 자동 트리거로?
모든 diff에 Opus+thinking 보안 리뷰를 돌리면 비싸다. diff에 `auth`/`crypto`/`sql`/`subprocess` 같은 키워드가 있을 때만 활성 — 높은 가치, 낮은 비용.

### 왜 "3회 연속 실패 = Escalate"?
gstack의 `/investigate` 철학: 3번 고쳤는데 같은 증상이면 문제는 코드가 아니라 **계획**이다. 더 많은 iteration으로 억지로 밀어붙이지 말고 gauntlet을 다시 돌려 scope/architecture를 재검토해야 한다.

---

## 참고 / 영감

- **[gstack](https://github.com/garrytan/gstack)** — Planning Gauntlet (`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/codex`, `/autoplan`), CSO, retro, careful/freeze 철학 차용
- **[obra/superpowers](https://github.com/obra/superpowers)** — TDD Iron Law, Red-Green-Refactor, 4-phase systematic debugging, evidence-based verification, Socratic brainstorming 차용
- **LangGraph** — cyclic state machine + checkpointing
- **Anthropic Claude API** — Extended thinking, prompt caching, tool use

---

## 라이센스

MIT.

---

## 기여

```bash
# 테스트 추가 후
pytest -v

# 철학 점검 체크리스트 (스스로에게 묻기):
# - [ ] 이 변경이 "evidence over claims"를 위반하지 않는가?
# - [ ] Iron Law를 위반하지 않는가? (테스트 없이 production code?)
# - [ ] Locked plan의 out_of_scope_guard에 들어갈 만한 걸 건드리지 않았나?
# - [ ] decisions.jsonl에 기록될 만한 결정이 있었다면 근거가 적혀 있는가?
```
