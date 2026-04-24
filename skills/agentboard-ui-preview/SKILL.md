---
name: agentboard-ui-preview
description: 4-layer TUI visual preview — ASCII mockup (Layer 0), Pilot text snapshot (Layer 1), SVG capture (Layer 2), scenes.yaml gallery (Layer 3). Invoke whenever a task has ui_surface=True so the user sees "what this looks like" at plan, first-GREEN, and approval gates — not just at the end.
when_to_use: Automatic after gauntlet arch.md on ui_surface=True (Layer 0). Automatic after first widget-mounting GREEN cycle in agentboard-tdd (Layer 1). Automatic before git push in agentboard-approval (Layer 2). Manual via scenes.yaml iteration when the goal directory contains that file (Layer 3). Also manually when the user says "show the UI", "preview", "mockup this", "snapshot the tui".
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

```bash
test -d .agentboard && test -f .mcp.json && echo OK || echo MISSING
```

- `MISSING` → exit with init hint.
- `OK` → proceed.

You are the **UI Preview Orchestrator**. Your job: make the TUI visible at every gate so the user never says "I can't see the change" at the end of a wedge. You compose four layers (0-3) of preview fidelity, each invoked at a specific chain point.

---

## Layer 0 — ASCII Mockup (Claude direct, pre-implementation)

**When**: immediately after `agentboard-gauntlet` writes arch.md and `task.metadata.ui_surface == True`.

**What**: produce an ASCII art mockup of the intended layout inside the arch.md (or a sibling `arch_mockup.md`). Include:
- Screen border and overall region partitioning
- Widget placement with labels (e.g. `[Plan]`, `[Dev 3/11]` for tabs/panels)
- Key bindings shown in mini-legend (e.g. `1/2/3/4 jump · ctrl+p pin`)
- Callouts for what changes vs. the existing UI (arrow + short note)

**Confirm with user via AskUserQuestion**: "This mockup captures the intent?" — options: confirm / request revision / switch approach. Record the confirmed mockup SHA in arch.md so gauntlet hash covers the visual intent.

**No MCP call** — this layer is purely Claude reasoning + markdown.

---

## Layer 1 — Text Snapshot (first widget GREEN)

**When**: in `agentboard-tdd`, right after the first atomic_step that mounts a widget visible to the user turns GREEN and `task.metadata.ui_surface == True`. Also re-run after each subsequent step that mutates visible UI state.

**What**: call the MCP tool to get a plain-text frame and stash it under `.agentboard/tui_snapshots/<goal_id>/layer1/<scene_id>.txt`.

**MCP invocation**:

```
agentboard_tui_capture_snapshot(
  project_root=<abs path>,
  scene_id="first_green" | "<atomic_step_id>",
  keys=[],                          # or scenario-specific sequence
  save_to="tui_snapshots/<goal_id>/layer1/<scene_id>.txt",
  include_svg=False,                # text-only for iteration speed
  fixture_goal_id=<gid-under-test>, # pin goal state for determinism
)
```

After capture, diff against the Layer 0 mockup ASCII and surface any drift (e.g. "mockup showed 4 tabs but capture shows 3 — mount wired incorrectly?"). If drift is material, invoke `agentboard-rca` — do NOT proceed silently.

---

## Layer 2 — SVG Snapshot (before push)

**When**: in `agentboard-approval`, after reviewer/parallel-review PASS and before `git push`. Triggered when `task.metadata.ui_surface == True`.

**What**: capture high-fidelity SVG frames (colors, borders, focus state preserved) and attach paths to the PR body.

**MCP invocation**:

```
agentboard_tui_capture_snapshot(
  project_root=<abs path>,
  scene_id="approval_final",
  keys=[],
  save_to="tui_snapshots/<goal_id>/layer2/final.txt",
  include_svg=True,                 # both .txt and .svg written
)
```

The SVG is embedded in `plan.md`'s `## Screenshots / Diagrams` section and linked from the PR description. Use multiple scenes (different key sequences) when a feature has more than one visible state.

---

## Layer 3 — Scene Gallery (scenes.yaml iteration)

**When**: if `.agentboard/goals/<goal_id>/scenes.yaml` exists, run the gallery sweep at Layer 2 time (approval) to cover every declared scene before push. Optional for small features; recommended once a goal has more than three visible states.

**scenes.yaml inline schema**:

```yaml
# .agentboard/goals/<goal_id>/scenes.yaml
scenes:
  - scene_id: plan_tab_default
    description: "Plan tab on boot, no plan_summary.md"
    keys: []
    tags: [plan, empty]
  - scene_id: dev_tab_with_iters
    description: "Dev tab after 3 tdd_green rows logged"
    keys: ["2"]
    tags: [dev]
  - scene_id: pinned_review
    description: "ctrl+p pinned while new decisions arrive"
    keys: ["ctrl+p", "4"]
    tags: [review, pin]
```

Fields:
- `scene_id` (required): unique id per goal; used as snapshot filename stem
- `description` (required): one-line human description (included in plan.md Screenshots section)
- `keys` (required, may be empty): list of Pilot key strings applied sequentially after mount
- `tags` (optional): free-form labels for grouping — used by future retro/gallery tooling

**Iteration**: for each entry, call `agentboard_tui_capture_snapshot(scene_id=..., keys=..., save_to="tui_snapshots/<gid>/layer3/<scene_id>.txt", include_svg=True)`. Write one heading per scene in the Screenshots section with description + .svg link.

---

## MCP Tool Reference

- `agentboard_tui_capture_snapshot` — primary engine. Pilot in-process, text + optional SVG, save_to path rooted at project_root.
- `agentboard_tui_render_smoke` — companion (NOT used by this skill). Real-pty crash gate only; different role.

---

## Handoff

| Layer | Upstream skill | Downstream action |
|---|---|---|
| 0 | agentboard-gauntlet | mockup confirmed → arch.md updated → gauntlet continues |
| 1 | agentboard-tdd | snapshot saved → drift check vs. Layer 0 → continue TDD or RCA |
| 2 | agentboard-approval | SVG saved → plan.md Screenshots section updated → push |
| 3 | agentboard-approval (when scenes.yaml present) | gallery sweep → all scenes saved → PR body lists them |

On ANY capture `crashed=True`: do NOT proceed to next layer / push. Surface the traceback and escalate to `agentboard-rca`.

---

## Common bypass attempts — NEVER allow

| User response | Correct reply |
|---|---|
| "snapshot 안 찍어도 됨" | "ui_surface=True 면 Layer 1 최소 1회 — 5초 걸림, 빠져나올 수 있는 것보다 싸다" |
| "SVG는 push 후에" | "approval Layer 2 목적이 push 전 시각 증거 — 순서 지키자" |
| "scenes.yaml 나중에 만들래" | "Layer 3은 선택 — scenes.yaml 없으면 Layer 1/2만 돌리고 끝" |
