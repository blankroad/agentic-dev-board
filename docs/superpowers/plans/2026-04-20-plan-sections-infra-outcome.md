# plan_sections Infra + Outcome Section — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `devboard.docs.plan_sections` — an idempotent `upsert_plan_section()` helper that appends/replaces named Markdown sections in `plan.md` — and wire `devboard-approval` SKILL.md so every push writes a `## Outcome` section. This is Goal #1 of the 5-goal `plan-as-living-doc` spec.

**Architecture:** New `src/devboard/docs/` package with a single pure-function helper that reuses existing `atomic_write` + `file_lock` from `storage.file_store`. A `PlanSection` string-enum pins the allowed section headings. Skill doc edit adds the `upsert_plan_section` call to the approval push flow. No new abstractions beyond the helper module.

**Tech Stack:** Python 3.12 · stdlib `re` for heading regex · `pathlib.Path` · existing `devboard.storage.file_store.atomic_write` + `file_lock` · pytest for tests.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `src/devboard/docs/__init__.py` | Create | Empty package marker |
| `src/devboard/docs/plan_sections.py` | Create | `PlanSection` enum + `upsert_plan_section()` |
| `tests/test_plan_sections.py` | Create | Helper unit tests (happy + 5 edge cases) |
| `skills/devboard-approval/SKILL.md` | Modify | Add Outcome write step between push success and task status update |
| `tests/test_approval_outcome_section.py` | Create | Skill doc string-assertion that the Outcome step is registered |

---

## Task 1 — Create the `docs` package

**Files:**
- Create: `src/devboard/docs/__init__.py`

- [ ] **Step 1: Create the empty package marker**

```bash
mkdir -p src/devboard/docs
: > src/devboard/docs/__init__.py
```

- [ ] **Step 2: Verify package imports cleanly**

Run: `python -c "import devboard.docs; print(devboard.docs.__name__)"`
Expected: `devboard.docs`

- [ ] **Step 3: Commit**

```bash
git add src/devboard/docs/__init__.py
git commit -m "feat(docs): introduce devboard.docs package for plan section helpers"
```

---

## Task 2 — Define `PlanSection` enum

**Files:**
- Create: `src/devboard/docs/plan_sections.py`
- Test: `tests/test_plan_sections.py`

- [ ] **Step 1: Write the failing test for the enum values**

```python
# tests/test_plan_sections.py
from __future__ import annotations

from pathlib import Path

import pytest


def test_plan_section_enum_has_four_known_members() -> None:
    """# guards: edge-case-red-rule
    edge: empty — enum must be stable and enumerable without instantiation."""
    from devboard.docs.plan_sections import PlanSection

    assert {m.value for m in PlanSection} == {
        "Metadata",
        "Outcome",
        "Screenshots / Diagrams",
        "Lessons",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plan_sections.py::test_plan_section_enum_has_four_known_members -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboard.docs.plan_sections'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/devboard/docs/plan_sections.py
from __future__ import annotations

from enum import Enum


class PlanSection(str, Enum):
    METADATA = "Metadata"
    OUTCOME = "Outcome"
    SCREENSHOTS = "Screenshots / Diagrams"
    LESSONS = "Lessons"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_plan_sections.py::test_plan_section_enum_has_four_known_members -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/devboard/docs/plan_sections.py tests/test_plan_sections.py
git commit -m "feat(docs): PlanSection enum — Metadata/Outcome/Screenshots/Lessons"
```

---

## Task 3 — Happy path: `upsert_plan_section` appends when missing

**Files:**
- Modify: `src/devboard/docs/plan_sections.py`
- Modify: `tests/test_plan_sections.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_plan_sections.py
def test_upsert_appends_when_section_missing(tmp_path: Path) -> None:
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section

    plan = tmp_path / "plan.md"
    plan.write_text("# Goal\n\n## Problem\n\nexisting body\n")

    upsert_plan_section(plan, PlanSection.OUTCOME, "status: pushed")

    text = plan.read_text()
    assert "## Problem" in text, "existing content must survive"
    assert "## Outcome" in text, "new section must appear"
    assert "status: pushed" in text
    # new section appended AFTER existing content
    assert text.index("## Problem") < text.index("## Outcome")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plan_sections.py::test_upsert_appends_when_section_missing -v`
Expected: FAIL with `ImportError: cannot import name 'upsert_plan_section'`

- [ ] **Step 3: Add minimal implementation**

Append to `src/devboard/docs/plan_sections.py`:

```python
from pathlib import Path

from devboard.storage.file_store import atomic_write, file_lock


def upsert_plan_section(plan_path: Path, section: PlanSection, content: str) -> None:
    """Replace or append a `## <section>` block in plan.md.

    If the heading exists, its body (up to the next `## ` heading or EOF)
    is replaced. If not, the block is appended at the end. Idempotent:
    re-calling with the same args yields the same file.
    """
    heading = f"## {section.value}"
    block = f"{heading}\n\n{content.rstrip()}\n"

    original = plan_path.read_text() if plan_path.exists() else ""

    if heading in _section_headings(original):
        new_text = _replace_section(original, heading, block)
    else:
        sep = "" if not original else ("" if original.endswith("\n\n") else ("\n" if original.endswith("\n") else "\n\n"))
        new_text = original + sep + block

    with file_lock(plan_path):
        atomic_write(plan_path, new_text)


def _section_headings(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("## ")]


def _replace_section(original: str, heading: str, new_block: str) -> str:
    lines = original.splitlines(keepends=True)
    try:
        start = next(i for i, ln in enumerate(lines) if ln.rstrip("\n") == heading)
    except StopIteration:
        return original + new_block
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "".join(lines[:start]) + new_block + "".join(lines[end:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_plan_sections.py::test_upsert_appends_when_section_missing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/devboard/docs/plan_sections.py tests/test_plan_sections.py
git commit -m "feat(docs): upsert_plan_section append-when-missing path"
```

---

## Task 4 — Idempotent replace when section exists

**Files:**
- Modify: `tests/test_plan_sections.py`

- [ ] **Step 1: Write the failing test for replace**

```python
def test_upsert_replaces_when_section_exists(tmp_path: Path) -> None:
    """# guards: edge-case-red-rule
    edge: cached stale — second upsert must replace, not stack."""
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section

    plan = tmp_path / "plan.md"
    plan.write_text("# G\n\n## Problem\n\nx\n")
    upsert_plan_section(plan, PlanSection.OUTCOME, "first")
    upsert_plan_section(plan, PlanSection.OUTCOME, "second")
    text = plan.read_text()
    assert text.count("## Outcome") == 1, f"must not stack: {text!r}"
    assert "second" in text
    assert "first" not in text
```

- [ ] **Step 2: Run test to verify it passes (already supported by Task 3 impl)**

Run: `pytest tests/test_plan_sections.py::test_upsert_replaces_when_section_exists -v`
Expected: PASS — the Task 3 implementation already handles replace via `_replace_section`.

If it does NOT pass, return to Task 3 impl — the branch is broken and must be fixed there, not here.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plan_sections.py
git commit -m "test(docs): upsert replaces existing section idempotently"
```

---

## Task 5 — Edge: empty / missing plan.md

**Files:**
- Modify: `tests/test_plan_sections.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_upsert_creates_file_when_missing(tmp_path: Path) -> None:
    """# guards: edge-case-red-rule
    edge: empty input — plan.md doesn't exist yet."""
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section

    plan = tmp_path / "plan.md"
    assert not plan.exists()
    upsert_plan_section(plan, PlanSection.METADATA, "goal_id: g_xxx")
    assert plan.exists()
    assert "## Metadata" in plan.read_text()
    assert "goal_id: g_xxx" in plan.read_text()


def test_upsert_on_empty_file_writes_single_block(tmp_path: Path) -> None:
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section

    plan = tmp_path / "plan.md"
    plan.write_text("")
    upsert_plan_section(plan, PlanSection.LESSONS, "learned X")
    text = plan.read_text()
    assert text.startswith("## Lessons"), f"no leading whitespace: {text!r}"
    assert "learned X" in text
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest tests/test_plan_sections.py::test_upsert_creates_file_when_missing tests/test_plan_sections.py::test_upsert_on_empty_file_writes_single_block -v`
Expected: PASS (the Task 3 impl covers both cases because `original = "" if not exists`, then the sep-logic avoids leading whitespace).

If the empty-file test fails with a leading `\n`, fix Task 3 impl:

```python
sep = "" if not original else ("" if original.endswith("\n\n") else ("\n" if original.endswith("\n") else "\n\n"))
```

already handles the empty-string case (first branch). If it doesn't, the condition order is off — inspect and fix in `plan_sections.py`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plan_sections.py
git commit -m "test(docs): upsert handles missing / empty plan.md"
```

---

## Task 6 — Edge: binary / non-UTF-8 plan.md (graceful skip)

**Files:**
- Modify: `src/devboard/docs/plan_sections.py`
- Modify: `tests/test_plan_sections.py`

- [ ] **Step 1: Write the failing test**

```python
def test_upsert_does_not_clobber_binary_plan(tmp_path: Path) -> None:
    """# guards: read-text-in-compose-must-catch-unicode
    edge: binary / non-UTF-8 file — must NOT overwrite a corrupted file
    with a fresh block (data loss risk). Should fall through quietly."""
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section

    plan = tmp_path / "plan.md"
    bad = b"\xff\xfe\x00garbled"
    plan.write_bytes(bad)

    # Must not raise
    upsert_plan_section(plan, PlanSection.OUTCOME, "status: pushed")

    # Original bytes preserved — we refused to touch it
    assert plan.read_bytes() == bad
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plan_sections.py::test_upsert_does_not_clobber_binary_plan -v`
Expected: FAIL — current implementation calls `read_text()` which raises `UnicodeDecodeError` AND/OR overwrites the file with an OUTCOME block (either outcome is a test failure).

- [ ] **Step 3: Wrap read in try/except and return early**

Replace the `original = plan_path.read_text() if plan_path.exists() else ""` line in `src/devboard/docs/plan_sections.py` with:

```python
if plan_path.exists():
    try:
        original = plan_path.read_text()
    except (OSError, UnicodeDecodeError):
        # Corrupted / binary plan.md — refuse to clobber. Skill caller
        # sees a no-op; user can fix the file and re-run.
        return
else:
    original = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_plan_sections.py::test_upsert_does_not_clobber_binary_plan -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/devboard/docs/plan_sections.py tests/test_plan_sections.py
git commit -m "fix(docs): upsert refuses to clobber binary plan.md"
```

---

## Task 7 — Edge: concurrent write under file_lock

**Files:**
- Modify: `tests/test_plan_sections.py`

- [ ] **Step 1: Write the failing test**

```python
def test_upsert_is_safe_under_concurrent_writes(tmp_path: Path) -> None:
    """# guards: edge-case-red-rule
    edge: concurrent mutation — two threads upserting different sections
    must both succeed without data loss."""
    import threading

    from devboard.docs.plan_sections import PlanSection, upsert_plan_section

    plan = tmp_path / "plan.md"
    plan.write_text("# Goal\n\n## Problem\n\np\n")

    def worker_metadata() -> None:
        upsert_plan_section(plan, PlanSection.METADATA, "goal_id: g_xxx")

    def worker_outcome() -> None:
        upsert_plan_section(plan, PlanSection.OUTCOME, "status: pushed")

    t1 = threading.Thread(target=worker_metadata)
    t2 = threading.Thread(target=worker_outcome)
    t1.start(); t2.start()
    t1.join(); t2.join()

    text = plan.read_text()
    # Both sections + the original must all exist
    assert "## Problem" in text
    assert "## Metadata" in text
    assert "## Outcome" in text
    assert "goal_id: g_xxx" in text
    assert "status: pushed" in text
```

- [ ] **Step 2: Run test to verify it passes (file_lock already wired in Task 3)**

Run: `pytest tests/test_plan_sections.py::test_upsert_is_safe_under_concurrent_writes -v`
Expected: PASS — the Task 3 impl wraps the write in `file_lock(plan_path)`, serializing the two threads.

If it fails with a lost section (one of the two writers clobbered the other), the lock scope is too narrow — widen it so BOTH the read AND the write happen inside `file_lock`. Fix in `plan_sections.py`:

```python
def upsert_plan_section(plan_path: Path, section: PlanSection, content: str) -> None:
    heading = f"## {section.value}"
    block = f"{heading}\n\n{content.rstrip()}\n"

    with file_lock(plan_path):
        if plan_path.exists():
            try:
                original = plan_path.read_text()
            except (OSError, UnicodeDecodeError):
                return
        else:
            original = ""

        if heading in _section_headings(original):
            new_text = _replace_section(original, heading, block)
        else:
            sep = "" if not original else ("" if original.endswith("\n\n") else ("\n" if original.endswith("\n") else "\n\n"))
            new_text = original + sep + block

        atomic_write(plan_path, new_text)
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_plan_sections.py src/devboard/docs/plan_sections.py
git commit -m "test(docs): upsert safe under concurrent writes"
```

---

## Task 8 — Wire `devboard-approval` SKILL.md to write Outcome

**Files:**
- Create: `tests/test_approval_outcome_section.py`
- Modify: `skills/devboard-approval/SKILL.md`

- [ ] **Step 1: Write the failing skill-doc assertion**

```python
# tests/test_approval_outcome_section.py
"""Verify devboard-approval SKILL.md instructs the Outcome upsert step."""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "devboard-approval"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL_PATH.read_text()


def test_approval_mentions_upsert_plan_section() -> None:
    assert "upsert_plan_section" in _text()


def test_approval_mentions_plan_section_outcome() -> None:
    assert "PlanSection.OUTCOME" in _text()


def test_approval_outcome_step_placed_between_push_and_status() -> None:
    """Step must run AFTER devboard_push_pr success (we know the PR URL
    and commit) and BEFORE devboard_update_task_status 'pushed' (so the
    doc reflects reality before the task is marked done)."""
    text = _text()
    push = text.find("devboard_push_pr")
    upsert = text.find("upsert_plan_section")
    status_update = text.find("devboard_update_task_status")
    assert push != -1 and upsert != -1 and status_update != -1
    assert push < upsert < status_update, (
        f"ordering wrong: push={push} upsert={upsert} status={status_update}"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_approval_outcome_section.py -v`
Expected: FAIL — three AssertionErrors (SKILL.md has no `upsert_plan_section` mention yet).

- [ ] **Step 3: Edit `skills/devboard-approval/SKILL.md`**

Find the section describing the push flow. After the `devboard_push_pr` line and BEFORE `devboard_update_task_status` / `devboard_checkpoint "converged"`, insert this block:

```markdown
### Step 4.5 — Write Outcome section to plan.md (MANDATORY)

After `devboard_push_pr` returns success (or a direct-push equivalent completes), write the publishable Outcome block to the goal's `plan.md` so the document records "what actually happened" next to the original plan:

```python
from devboard.docs.plan_sections import PlanSection, upsert_plan_section
from pathlib import Path

plan_path = Path(project_root) / ".devboard" / "goals" / goal_id / "plan.md"
outcome = (
    f"- Status: pushed\n"
    f"- Final commit: {final_commit_sha}\n"
    f"- PR: {pr_url or 'direct push to origin/main'}\n"
    f"- Iterations: {iterations}\n"
    f"- Tests: {tests_total} passing\n"
    f"- Red-team: {redteam_rounds} rounds, final {redteam_final_verdict}\n"
    f"- CSO: {cso_verdict or 'not required'}\n"
    f"- Pushed at: {utcnow_iso}"
)
upsert_plan_section(plan_path, PlanSection.OUTCOME, outcome)
```

The helper is idempotent — re-running approval after a fix produces the same single-section result, no stacking. The `plan.json` locked_hash is unaffected (Outcome lives in plan.md only).

After this write, proceed to `devboard_checkpoint "converged"` and `devboard_update_task_status status="pushed"`.
```

Place this heading block AFTER the existing description of `devboard_push_pr` and BEFORE the `devboard_update_task_status` / `converged` checkpoint instructions. If the SKILL.md does not yet have Step numbering at that depth, use the heading level consistent with surrounding steps.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_approval_outcome_section.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Full suite regression**

Run: `pytest`
Expected: PASS — prior test count + 10 new tests from Tasks 2-8.

- [ ] **Step 6: Commit**

```bash
git add tests/test_approval_outcome_section.py skills/devboard-approval/SKILL.md
git commit -m "feat(approval): write ## Outcome section to plan.md after push"
```

---

## Task 9 — Install SKILL.md change to local skills tree

**Files:**
- Modify: `~/.local/share/agentic-dev-board/skills/devboard-approval/SKILL.md` (via install.sh)

- [ ] **Step 1: Push to origin**

```bash
git push origin main
```

- [ ] **Step 2: Run install.sh to pull + install locally**

```bash
bash install.sh
```

Expected output includes `updating /Users/ctmctm/.local/share/agentic-dev-board` and `✓ agentic-dev-board installed`.

- [ ] **Step 3: Verify installed skill has the new Outcome step**

Run: `grep -c "upsert_plan_section" ~/.local/share/agentic-dev-board/skills/devboard-approval/SKILL.md`
Expected: `1` (or more — the mention appears at least once).

No commit (install.sh does not produce repo-local changes).

---

## Self-Review

**Spec coverage check** — walked `docs/superpowers/specs/2026-04-20-plan-as-living-doc-design.md` Goal #1 scope:

| Spec item | Task |
|---|---|
| `src/devboard/docs/__init__.py` + `plan_sections.py` | Tasks 1, 2 |
| `upsert_plan_section()` helper + `PlanSection` enum | Tasks 2, 3 |
| `devboard-approval` SKILL.md: push 성공 후 Outcome write 단계 추가 | Task 8 |
| TDD happy: append when missing | Task 3 |
| TDD edge empty: plan.md 빈 파일일 때 | Task 5 |
| TDD edge replace: 기존 섹션 replace (idempotent) | Task 4 |
| TDD edge binary: plan.md 가 non-UTF-8 일 때 graceful | Task 6 |
| TDD edge concurrent: file_lock 동시 write | Task 7 |

All Goal #1 spec items mapped. No gaps.

**Placeholder scan:** no "TBD", no "TODO", no "add appropriate error handling", no "similar to Task N". All code blocks complete.

**Type consistency:** `PlanSection.OUTCOME` used verbatim across all tasks. `upsert_plan_section(plan_path, section, content)` signature identical in Task 3 impl, Task 8 skill doc, and tests. Return type `None` consistent.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-20-plan-sections-infra-outcome.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
