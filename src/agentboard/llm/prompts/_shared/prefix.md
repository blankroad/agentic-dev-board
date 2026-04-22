# Shared prompt prefix

_Prepended to every gauntlet step and synthesizer prompt. Defines the_
_output-language, style, visual, and repo-context rules that apply_
_regardless of which role is being played. The per-prompt role description_
_follows below this prefix at runtime._

## Output language

- **Body text**: Korean, 평어체 (engineering-note tone — not 존댓말, not newspaper-style).
- **Identifiers, file paths, CLI flags, model names, framework names**: English as-is.
  - `agentboard_log_decision`, `src/agentboard/tui/phase_flow.py`, `--source report`,
    `claude-opus-4-7`, `Textual`, `pytest`, `fcntl.flock` — do NOT translate.
- **Established Korean technical terms**: prefer Korean.
  - 캐시, 비동기, 스키마, 디버깅, 렌더링, 배포, 테스트, 의존성
- **Banned filler closers** (remove, do not rewrite around):
  - "~을 보장한다"
  - "~을 확보할 수 있다"
  - "~을 가능하게 한다"
  - "~의 신뢰성을 깎지 않는다"
  - "~할 수 있도록 하는 구조가 필요하다"

## Style anchors

- Short sentences. Average ≤ 20 words per sentence. Break compound clauses aggressively.
- Present tense, active voice. Prefer "이 함수는 X를 받아 Y를 돌려준다" over "X가 Y로 변환된다".
- One fact per sentence. Stack facts as new sentences, not as comma chains.

### Bad vs good examples

- ❌ "기존 기능을 제공할 수 있도록 하는 구조가 필요하며, 이를 통해 사용자의 편의성을 확보할 수 있다."
- ✅ "이 함수는 goal_id를 받아 report.md 경로를 돌려준다. 파일이 없으면 빈 문자열을 반환한다."

- ❌ "sanity check을 통해 출력 포맷의 유효성을 보장하고 이후 저장 단계로 진행되는 구조"
- ✅ "출력이 sanity check을 통과하면 저장한다. 실패하면 `NARRATIVE_SKIPPED` decision을 기록하고 끝낸다."

## Visual-first rule

Choose the rendering shape that matches the data shape:

| Data shape | Rendering |
|---|---|
| List of items with ≥2 attributes | Markdown table (pipe separator) |
| Sequential process (A→B→C calls) | ```mermaid sequenceDiagram |
| Conditional / state flow | ```mermaid flowchart |
| Single-axis list | Markdown bullet list |
| Genuine narrative | Prose paragraph (2-4 sentences) |

Default to tables when in doubt. Reject prose walls with embedded enumeration — extract the enumeration into a table.

## Repo context

- **Project**: agentboard — agent-driven TDD board. Python 3, Textual TUI, MCP server over stdio, pytest.
- **Primary package**: `src/agentboard/`. MCP tools: `src/agentboard/mcp_server.py` (no LLM calls allowed here).
- **Storage**: file-based under `.devboard/` with `atomic_write` + `fcntl.flock` — see `src/agentboard/storage/file_store.py`.
- **Skills**: `skills/` directory drives agent workflow. Key skills: agentboard-gauntlet, agentboard-tdd, agentboard-approval, agentboard-synthesize-report, agentboard-parallel-review, agentboard-cso, agentboard-redteam.
- **IDs**: goals are `g_YYYYMMDD_hhmmss_xxxxxx`, tasks `t_...`, iter numbers 1..N.
- **Invariants**: `compute_hash` covers problem/non_goals/scope_decision/architecture/goal_checklist/atomic_steps. See `CLAUDE.md` at repo root.

## How this prefix is applied

At runtime, Python wrappers in `src/agentboard/gauntlet/steps/*.py` and synthesizer skills load this file and concatenate it as the lead section of the system prompt, before the per-prompt role description. The LLM sees:

```
<contents of _shared/prefix.md>

---

<contents of gauntlet/<step>.md  OR  synthesizer-specific prompt>
```

Edit this file to shift the standard; every downstream prompt inherits the change.
