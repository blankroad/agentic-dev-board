# agentic-dev-board — 5분 Quickstart

> 목표: 5분 안에 devboard 설치 → Claude Code로 첫 기능 구현 → `.devboard/`에 쌓인 이력 확인.

## 필요한 것

- Python 3.11+
- Claude Code (또는 호환 에이전트)
- 선택: `gh` CLI (PR 자동 생성용)

## 1. 설치 (30초)

```bash
git clone https://github.com/blankroad/agentic-dev-board.git
cd agentic-dev-board
python -m venv .venv && source .venv/bin/activate
pip install -e .

# devboard CLI 동작 확인
devboard --help
```

## 2. 새 프로젝트에 적용 (1분)

```bash
mkdir ~/my-first-devboard-project && cd ~/my-first-devboard-project

devboard init              # .devboard/ 스캐폴드
devboard install           # skills + hooks + .mcp.json 설치
devboard audit             # 준비 상태 확인 — 모두 초록불이어야 함
```

**글로벌 설치** (모든 프로젝트에서 skill 자동 사용):
```bash
devboard install --scope global    # ~/.claude/skills/ 에 복사
# 각 프로젝트에서는 hooks + MCP config만:
cd my-project && devboard install --no-skills
```

## 3. 첫 goal + Claude Code 세션 (2분)

```bash
devboard goal add "Create a palindrome checker: is_palindrome(s, ignore_case=True, ignore_spaces=True). Empty string = True. Include 5+ pytest tests."

claude    # Claude Code 실행
```

Claude Code 세션 안에서:

```
build this goal using devboard skills — gauntlet → tdd → approval.
한국어로 진행 상황 보고해줘.
```

**기대 동작**:
- `devboard-gauntlet` 스킬 auto-invoke → 5-step planning → `plan.md` + SHA256 hash 생성
- `devboard-tdd` 스킬 auto-invoke → 각 atomic_step마다 RED → GREEN → REFACTOR
- 각 단계 `.devboard/runs/<run_id>.jsonl` + `decisions.jsonl`에 기록
- 수렴 후 `devboard-approval` 이 squash 정책 묻고 PR 생성

## 4. 실시간 관찰 (다른 터미널)

```bash
cd ~/my-first-devboard-project
devboard watch                 # state transition live stream
# 또는
devboard watch --all           # runs + decisions 동시 tail
# 또는
devboard status                # 한 화면 요약
# 또는
devboard board                 # Textual TUI
```

## 5. 끝난 뒤

```bash
devboard retro --save          # 이번 세션 stats 저장
devboard learnings list        # 이 프로젝트의 확보된 learnings
cat .devboard/goals/*/plan.md  # 고정된 plan
cat .devboard/runs/*.jsonl     # state transition 이력
```

---

## 주요 워크플로

### 기존 goal 재계획 (rethink)
```bash
devboard goal list
# Claude Code: "rethink g_xxxxx"  또는  "re-run gauntlet for g_xxxxx"
```

### 시간여행
```bash
devboard replay run_abc --from 3 --variant "try iterative approach instead"
# 새 run_id 받음 → Claude Code에서 해당 run 이어받아 탐색
```

### 팀 공유
```bash
devboard skills export -o my-team-skills.zip
# 동료가 받으면:
devboard skills import my-team-skills.zip --scope global
```

### 여러 언어 (JS/TS/Go/Rust)
`devboard_verify` 는 프로젝트 루트에서 자동 감지:

| 파일 | 감지되는 runner |
|---|---|
| `package.json` with `"test"` script | `npm test` |
| `vitest.config.*` | `npx vitest run` |
| `jest.config.*` | `npx jest` |
| `go.mod` | `go test ./...` |
| `Cargo.toml` | `cargo test` |
| (default) | `pytest -v` |

---

## 문제 해결

### "No runs yet"가 계속 뜸
Claude Code 세션 안에서 skill이 **발동 안 했음**. 아래 중 하나:

1. **skill이 로드됐는지 확인** — `.claude/skills/devboard-*/SKILL.md` 파일 존재 OR `~/.claude/skills/`에 있는지
2. **`.mcp.json` 이 프로젝트 루트에 있는지** — `cat .mcp.json`
3. **`.mcp.json`의 python path가 유효한지** — `devboard install --python $(which python)` 으로 재설치
4. **명시적 invoke** — "use devboard-gauntlet + devboard-tdd"
5. **Claude Code `/mcp` 명령** — 연결된 MCP 서버 목록 확인

### 훅이 작동 안 함
`.claude/settings.json`이 프로젝트 루트에 있어야 함. `devboard install` 이 자동 생성하지만, Claude Code는 **세션 시작 시에만** settings를 읽음. 이미 연 세션이면 재시작 필요.

### 한국어가 아닌 영어로 응답
`SKILL.md` 상단 `> **언어**: ... 한국어 ...` 블록이 강제해야 하는데 Claude Code가 skill context 밖에서 응답할 때는 적용 안 될 수 있음. 프로젝트 `.claude/settings.json`에 `"language": "korean"` 추가해서 전역으로 강제 가능.

### `gh` 없음
`devboard-approval` 이 PR 생성 실패 → push만 실행하고 사용자에게 수동 PR 생성 요청. 설치 권장:
```bash
brew install gh && gh auth login
```

---

## 다음 단계

- `README.md` — 전체 아키텍처
- `skills/*/SKILL.md` — 각 skill이 하는 일
- `src/devboard/mcp_server.py` — 24개 MCP tool 스펙
