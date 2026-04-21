"""Build OverviewPayload dict from on-disk devboard artifacts.

Pure, read-only. No LLM calls. Each section (purpose, plan_digest,
iterations, current_state, learnings, followups) is produced by an
independent try/except so partial failures degrade gracefully instead
of erasing all 5 tabs.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import TypedDict


class OverviewPayload(TypedDict):
    purpose: str
    plan_digest: dict[str, object]
    iterations: list[dict[str, object]]
    current_state: dict[str, object]
    learnings: list[dict[str, object]]
    followups: list[str]
    # As-Is → To-Be framing: one delta per task, not a per-iter timeline.
    code_delta: dict[str, object]  # {base_commit, head_commit, files[], adds, dels}
    step_shipping: list[dict[str, object]]  # per atomic_step: shipping iter/ts/verdict
    risk_delta: dict[str, object]  # {resolved[], remaining[], learnings[], todos[]}
    # AI-synthesized As-Is → To-Be Markdown saved at goals/<gid>/report.md.
    # Empty string when the file is missing — overview_render falls back to
    # the legacy plan_digest layout in that case.
    report_md: str


_PREMISE_BULLET = re.compile(r"^-\s+(.+?)\s*$")
_DIFF_PLUS_FILE = re.compile(r"^\+\+\+\s+b/(.+)$")
_STEP_ID_TOKEN = re.compile(r"\bs_(\d{3})\b")


def _match_step_for_iter(
    it: int,
    reasoning: str,
    atomic_steps: list[dict],
) -> dict | None:
    """Resolve an iter number to its atomic_step. Priority:
    1. regex — first `s_NNN` in `reasoning` that exists in atomic_steps
    2. index heuristic — iter N → atomic_steps[N-1] when in range
    3. None — caller substitutes '?' / defaults
    """
    if not atomic_steps:
        return None
    known_ids = {s.get("id") for s in atomic_steps if isinstance(s, dict)}
    m = _STEP_ID_TOKEN.search(reasoning or "")
    if m:
        candidate = f"s_{m.group(1)}"
        if candidate in known_ids:
            for s in atomic_steps:
                if isinstance(s, dict) and s.get("id") == candidate:
                    return s
    idx = it - 1
    if 0 <= idx < len(atomic_steps):
        s = atomic_steps[idx]
        if isinstance(s, dict):
            return s
    return None


def _load_raw_atomic_steps(plan_json_path: Path) -> list[dict]:
    """Load plan.json's atomic_steps as raw list of dicts.

    Unlike _extract_plan_digest which projects a trimmed subset, this returns
    the full step objects so iteration cross-ref can access behavior/
    test_file/test_name/impl_file verbatim.
    """
    try:
        data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    steps = data.get("atomic_steps") or []
    return [s for s in steps if isinstance(s, dict)]


def _read_task_status(goal_dir: Path, task_id: str | None) -> str:
    """Read `status` from task.json, falling back to 'in_progress' on any
    error. Used by build_overview_payload for current_state.status."""
    if task_id is None:
        return "in_progress"
    task_json = goal_dir / "tasks" / task_id / "task.json"
    try:
        data = json.loads(task_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "in_progress"
    status = data.get("status")
    if isinstance(status, str) and status:
        return status
    return "in_progress"


def _extract_purpose(brainstorm_path: Path) -> str:
    try:
        text = brainstorm_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    in_premises = False
    for line in text.splitlines():
        if line.strip().lower().startswith("## premises"):
            in_premises = True
            continue
        if in_premises:
            m = _PREMISE_BULLET.match(line)
            if m:
                return m.group(1)
            if line.startswith("##"):
                break
    return ""


def _extract_touched_files(diff_path: Path) -> list[str]:
    try:
        text = diff_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[str] = []
    for line in text.splitlines():
        m = _DIFF_PLUS_FILE.match(line)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def _diff_stats(diff_path: Path) -> dict[str, int]:
    try:
        text = diff_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"adds": 0, "dels": 0}
    adds = 0
    dels = 0
    for line in text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            adds += 1
        elif line.startswith("-"):
            dels += 1
    return {"adds": adds, "dels": dels}


# Per-iter "primary row" selection. Decisions.jsonl logs tdd_red → tdd_green →
# tdd_refactor for every cycle. tdd_refactor=SKIPPED is the *last* row but the
# least informative — it carries no reasoning, no verdict signal. tdd_green
# carries the real "why it shipped" narrative, so it wins. Fallback to tdd_red
# (early failures), then anything else, then tdd_refactor only if nothing else
# exists for the iter. Also excludes bool from the int check — `True` is an int
# in Python and would otherwise pollute the iteration list.
_PHASE_PRIORITY: dict[str, int] = {
    "tdd_green": 100,
    "tdd_red": 50,
    "eng_review": 40,
    "review": 40,
    "parallel_review": 40,
    "tdd_refactor": -10,
}


def _git_numstat_for_iter(
    project_root: Path, iter_n: int, task_id: str | None = None
) -> tuple[list[str], dict[str, int]]:
    """Look up numstat for the commit whose subject carries ``iter N [`` for
    this specific task.

    The ``task <task_id>`` scope is critical — without it, ``iter 1 [`` would
    match every prior task's first commit too.

    Returns ([], {0,0}) when git is unavailable, no match, or on any failure —
    caller falls back to the legacy iter_N.diff parser.
    """
    # Conservative: if task_id is not scoped, do not run git (would leak other
    # tasks' commits into this iter's file list).
    if not task_id:
        return ([], {"adds": 0, "dels": 0})
    grep = f"task {task_id} iter {iter_n} \\["
    try:
        proc = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--numstat",
                "--format=",
                f"--grep={grep}",
                "--extended-regexp",
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ([], {"adds": 0, "dels": 0})
    if proc.returncode != 0 or not proc.stdout.strip():
        return ([], {"adds": 0, "dels": 0})
    touched: list[str] = []
    adds_total = 0
    dels_total = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        if not path or path in touched:
            continue
        touched.append(path)
        try:
            adds_total += int(a)
            dels_total += int(d)
        except ValueError:
            # binary (- / -) — count as touched but not summed
            continue
    return touched, {"adds": adds_total, "dels": dels_total}


def _extract_iterations(
    task_dir: Path,
    project_root: Path | None = None,
    task_id: str | None = None,
    atomic_steps: list[dict] | None = None,
) -> list[dict[str, object]]:
    decisions = task_dir / "decisions.jsonl"
    if not decisions.exists():
        return []
    try:
        text = decisions.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    # Group every decision row by iter number.
    by_iter: dict[int, list[dict]] = {}
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        it = entry.get("iter")
        # Strict int check — True/False would pass isinstance(int) otherwise.
        if isinstance(it, bool) or not isinstance(it, int):
            continue
        by_iter.setdefault(it, []).append(entry)

    rows: list[dict[str, object]] = []
    for it in sorted(by_iter.keys()):
        entries = by_iter[it]
        # Pick the most informative row per iter via _PHASE_PRIORITY.
        primary = max(
            entries,
            key=lambda e: _PHASE_PRIORITY.get(str(e.get("phase", "")), 0),
        )
        # Prefer live git numstat (real unified diff, accurate); fallback to
        # legacy iter_N.diff parser when git lookup is empty.
        touched: list[str] = []
        stats: dict[str, int] = {"adds": 0, "dels": 0}
        if project_root is not None:
            touched, stats = _git_numstat_for_iter(project_root, it, task_id)
        if not touched:
            diff_path = task_dir / "changes" / f"iter_{it}.diff"
            touched = _extract_touched_files(diff_path)
            stats = _diff_stats(diff_path)
        reasoning_text = str(primary.get("reasoning", ""))
        matched_step = _match_step_for_iter(it, reasoning_text, atomic_steps or [])
        step_id = matched_step.get("id", "?") if matched_step else "?"
        rows.append(
            {
                "iter": it,
                "phase": primary.get("phase", ""),
                "verdict": primary.get("verdict_source", ""),
                "reasoning": reasoning_text,
                "ts": primary.get("ts", ""),
                "touched_files": touched,
                "diff_stats": stats,
                "step_id": step_id,
                "behavior": matched_step.get("behavior", "") if matched_step else "",
                "test_file": matched_step.get("test_file", "") if matched_step else "",
                "test_name": matched_step.get("test_name", "") if matched_step else "",
                "impl_file": matched_step.get("impl_file", "") if matched_step else "",
            }
        )
    return rows


def _git_run(args: list[str], cwd: Path, timeout: float = 5.0) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _task_base_commit(project_root: Path, task_id: str) -> str:
    """Find the commit immediately BEFORE the first commit of this task.

    Strategy: `git log --grep="task <task_id>"` gives all this-task commits
    newest-first; the last line is the oldest. Its parent is the baseline.
    Falls back to empty string if git unavailable or no commits matched
    (task-in-progress without any shipped iters yet).
    """
    out = _git_run(
        [
            "log",
            "--all",
            "--reflog",
            f"--grep=task {task_id}",
            "--format=%H",
        ],
        cwd=project_root,
    )
    if not out.strip():
        return ""
    shas = [line for line in out.splitlines() if line.strip()]
    if not shas:
        return ""
    oldest_task_sha = shas[-1]
    parent_out = _git_run(
        ["rev-parse", f"{oldest_task_sha}^"],
        cwd=project_root,
    )
    return parent_out.strip()


def _code_delta(project_root: Path, base: str, head: str = "HEAD") -> dict[str, object]:
    """`git diff --numstat base..head` → {files, adds, dels, base, head}.

    Returns empty stats if base is empty (new task, nothing shipped yet).
    """
    if not base:
        return {"base_commit": "", "head_commit": "", "files": [], "adds": 0, "dels": 0}
    head_sha = _git_run(["rev-parse", head], cwd=project_root).strip()
    out = _git_run(["diff", "--numstat", f"{base}..{head}"], cwd=project_root)
    files: list[dict[str, object]] = []
    adds_total = 0
    dels_total = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        if not path:
            continue
        if a == "-" and d == "-":
            files.append({"path": path, "adds": "bin", "dels": "bin"})
            continue
        try:
            ai, di = int(a), int(d)
        except ValueError:
            continue
        files.append({"path": path, "adds": ai, "dels": di})
        adds_total += ai
        dels_total += di
    return {
        "base_commit": base[:8],
        "head_commit": head_sha[:8] if head_sha else "",
        "files": files,
        "adds": adds_total,
        "dels": dels_total,
    }


def _step_shipping(
    atomic_steps: list[dict[str, object]], iterations: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Cross-reference plan.json atomic_steps with decisions GREEN iters.

    Priority per iter:
    1. regex — first `s_NNN` in reasoning that matches a known step id
    2. index heuristic — iter N → atomic_steps[N-1] (when reasoning lacks
       the token, which is the common case since TDD reasoning often
       describes the change, not restates the step id)

    An iter that matches multiple atomic_steps only claims the first
    unclaimed one (setdefault preserves earliest ship_ts). Falls back to
    the step's own `completed` flag for legacy records.
    """
    known_ids = {str(s.get("id", "")) for s in atomic_steps}
    green_by_step: dict[str, dict[str, object]] = {}
    for it in iterations:
        phase = str(it.get("phase", ""))
        if not phase.startswith("tdd_green"):
            continue
        reasoning = str(it.get("reasoning", ""))
        matched: str | None = None
        # 1) regex match that corresponds to a real step id
        m = re.search(r"\b(s_\d{3})\b", reasoning)
        if m and m.group(1) in known_ids:
            matched = m.group(1)
        # 2) index heuristic: iter N → atomic_steps[N-1]
        if matched is None:
            it_n = it.get("iter")
            if isinstance(it_n, int) and 1 <= it_n <= len(atomic_steps):
                candidate = str(atomic_steps[it_n - 1].get("id", ""))
                if candidate:
                    matched = candidate
        if matched:
            green_by_step.setdefault(matched, it)

    out: list[dict[str, object]] = []
    for s in atomic_steps:
        sid = str(s.get("id", ""))
        shipped = green_by_step.get(sid)
        out.append(
            {
                "id": sid,
                "behavior": s.get("behavior", ""),
                "impl_file": s.get("impl_file", ""),
                "test_file": s.get("test_file", ""),
                "shipped": shipped is not None or bool(s.get("completed")),
                "ship_iter": shipped.get("iter") if shipped else None,
                "ship_ts": shipped.get("ts", "") if shipped else "",
                "ship_verdict": shipped.get("verdict", "") if shipped else "",
            }
        )
    return out


def _risk_delta(
    plan_data: dict[str, object],
    decisions: list[dict[str, object]],
) -> dict[str, object]:
    """Build As-Is risks (from plan.known_failure_modes) vs resolved/remaining.

    Classification rules (R5 cross-ref):
    1. Final parallel_review verdict == CLEAN → all planned risks resolved.
    2. Otherwise: a planned risk is resolved if any tdd_green reasoning
       mentions a keyword from the risk text after the severity prefix.
    3. Unmatched risks stay in `remaining`.
    `KNOWN_RISK` verdict rows are appended to `remaining` as new risks.
    """
    planned = [str(r) for r in (plan_data.get("known_failure_modes") or [])]
    followups = [str(x) for x in (plan_data.get("non_goals") or []) if x]

    # Keyword match — per-risk evidence from tdd_green + review + approval
    # reasoning. parallel_review=CLEAN is a global signal (shown separately
    # in the Review tab) and does NOT blanket-promote risks without
    # per-risk evidence — redteam FM#6 (avoid false-resolved risks where
    # CLEAN was granted on unrelated checks).
    evidence_corpus = " ".join(
        str(d.get("reasoning", ""))
        for d in decisions
        if str(d.get("phase", "")).startswith("tdd_green")
        or str(d.get("phase", "")) in ("review", "approval")
    ).lower()

    def _referenced(risk: str) -> bool:
        after_colon = risk.split(":", 1)[-1]
        key = after_colon.strip().split(" ")[0].lower()
        return bool(key) and key in evidence_corpus

    resolved = [r for r in planned if _referenced(r)]
    remaining = [r for r in planned if r not in resolved]

    # New risks surfaced during execution (not in plan).
    new_risks = [
        str(d.get("reasoning", ""))
        for d in decisions
        if str(d.get("verdict_source", "")) == "KNOWN_RISK"
    ]

    return {
        "resolved": resolved,
        "remaining": remaining + new_risks,
        "followups": followups,
    }


def _extract_followups(plan_json_path: Path) -> list[str]:
    try:
        data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    ng = data.get("non_goals") or []
    return [str(x) for x in ng if x]


def _load_learnings_from_files(project_root: Path) -> list[dict[str, object]]:
    """R5 fix — previous _extract_learnings looked for a non-existent
    .devboard/learnings.jsonl. Actual learnings are stored as individual
    .md files with YAML frontmatter via FileStore.save_learning. This
    helper uses FileStore.list_learnings() (directory-based) and parses
    each file's frontmatter + first-body-paragraph for summary display.
    """
    try:
        from agentboard.storage.file_store import FileStore

        store = FileStore(project_root)
        paths = store.list_learnings()
    except Exception:
        return []
    out: list[dict[str, object]] = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        name = p.stem
        tags: list[str] = []
        category = ""
        confidence = 0.0
        summary = ""
        # Minimal YAML frontmatter parse — the save path writes
        # `---\nkey: val\n---\n...body` but we only extract what we need.
        body = text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                frontmatter = text[3:end]
                body = text[end + 4:].lstrip("\n")
                for line in frontmatter.splitlines():
                    line = line.strip()
                    if ":" not in line:
                        continue
                    k, _, v = line.partition(":")
                    k = k.strip().lower()
                    v = v.strip().strip("\"'")
                    if k == "name" and v:
                        name = v
                    elif k == "tags":
                        if v.startswith("[") and v.endswith("]"):
                            tags = [t.strip().strip("\"'") for t in v[1:-1].split(",") if t.strip()]
                    elif k == "category":
                        category = v
                    elif k == "confidence":
                        try:
                            confidence = float(v)
                        except ValueError:
                            pass
        # Summary = first non-heading, non-empty body paragraph (first 160
        # chars, ended at sentence boundary when available).
        for raw in body.splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            summary = s[:160]
            break
        out.append(
            {
                "name": name,
                "tags": tags,
                "category": category,
                "confidence": confidence,
                "summary": summary,
            }
        )
    return out


def _extract_learnings(learnings_path: Path) -> list[dict[str, object]]:
    """Legacy path — kept so existing callers importing this symbol keep
    working. Prefer `_load_learnings_from_files(project_root)` for new
    code; this one is a no-op when the .jsonl doesn't exist (it never
    does in current layouts)."""
    if not learnings_path.exists():
        return []
    try:
        text = learnings_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[dict[str, object]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            out.append(
                {
                    "name": entry.get("name", ""),
                    "content": entry.get("content", ""),
                    "confidence": entry.get("confidence", 0.0),
                }
            )
    return out


def _extract_plan_digest(plan_json_path: Path) -> dict[str, object]:
    try:
        data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    steps = data.get("atomic_steps") or []
    # Strict boolean-True only — plan.json with completed: "false" (string)
    # is truthy in Python and would otherwise inflate the done count.
    done = sum(1 for s in steps if isinstance(s, dict) and s.get("completed") is True)
    step_list = [
        {
            "id": s.get("id", ""),
            "behavior": s.get("behavior", ""),
            "impl_file": s.get("impl_file", ""),
            "test_file": s.get("test_file", ""),
            "completed": s.get("completed") is True,
        }
        for s in steps
        if isinstance(s, dict)
    ]
    return {
        "locked_hash": data.get("locked_hash", ""),
        "scope_decision": data.get("scope_decision", ""),
        "atomic_steps_total": len(steps),
        "atomic_steps_done": done,
        "atomic_steps": step_list,
    }


def build_overview_payload(
    project_root: Path,
    goal_id: str,
    task_id: str | None = None,
) -> OverviewPayload:
    goal_dir = project_root / ".devboard" / "goals" / goal_id
    try:
        purpose = _extract_purpose(goal_dir / "brainstorm.md")
    except Exception:
        purpose = ""
    try:
        plan_digest = _extract_plan_digest(goal_dir / "plan.json")
    except Exception:
        plan_digest = {}
    # Load raw atomic_steps for iteration cross-ref (R3: step_id/behavior/
    # test_file/impl_file fields on iterations[i]). Separate from plan_digest
    # which has a trimmed projection.
    raw_atomic_steps = _load_raw_atomic_steps(goal_dir / "plan.json")
    iterations: list[dict[str, object]] = []
    if task_id is not None:
        try:
            iterations = _extract_iterations(
                goal_dir / "tasks" / task_id,
                project_root=project_root,
                task_id=task_id,
                atomic_steps=raw_atomic_steps,
            )
        except Exception:
            iterations = []
    # current_state.status is sourced from task.json when available; fall back
    # to "in_progress" (task exists but task.json unreadable) or
    # "awaiting_task" (no task_id). R1 fix — was hardcoded "in_progress".
    task_status = _read_task_status(goal_dir, task_id)
    current_state: dict[str, object] = (
        {"status": "awaiting_task"} if task_id is None else {"status": task_status}
    )
    if iterations:
        last = iterations[-1]
        current_state = {
            "status": task_status,
            "last_iter": last["iter"],
            "last_phase": last["phase"],
            "last_verdict": last["verdict"],
            "last_ts": last["ts"],
        }
    try:
        followups = _extract_followups(goal_dir / "plan.json")
    except Exception:
        followups = []
    try:
        learnings = _load_learnings_from_files(project_root)
    except Exception:
        learnings = []

    # As-Is → To-Be delta sections.
    code_delta: dict[str, object] = {
        "base_commit": "", "head_commit": "", "files": [], "adds": 0, "dels": 0,
    }
    step_shipping: list[dict[str, object]] = []
    risk_delta: dict[str, object] = {"resolved": [], "remaining": [], "followups": []}
    if task_id is not None:
        try:
            base = _task_base_commit(project_root, task_id)
            code_delta = _code_delta(project_root, base)
        except Exception:
            pass
        try:
            atomic_steps = list(plan_digest.get("atomic_steps") or [])  # type: ignore[arg-type]
            step_shipping = _step_shipping(atomic_steps, iterations)
        except Exception:
            pass
        try:
            plan_data: dict[str, object] = {}
            plan_path = goal_dir / "plan.json"
            if plan_path.exists():
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            # decisions rows live in task_dir/decisions.jsonl — already parsed
            # once inside _extract_iterations; re-parse cheaply here for risk
            # corpus instead of plumbing state across calls.
            decisions_raw: list[dict[str, object]] = []
            dpath = goal_dir / "tasks" / task_id / "decisions.jsonl"
            if dpath.exists():
                for raw in dpath.read_text(encoding="utf-8").splitlines():
                    if not raw.strip():
                        continue
                    try:
                        e = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(e, dict):
                        decisions_raw.append(e)
            risk_delta = _risk_delta(plan_data, decisions_raw)
        except Exception:
            pass

    # report.md is AI-synthesized by agentboard-synthesize-report and
    # consumed as raw Markdown by overview_render.render_overview_body.
    report_md = ""
    report_path = goal_dir / "report.md"
    if report_path.exists():
        try:
            report_md = report_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            report_md = ""

    return OverviewPayload(
        purpose=purpose,
        plan_digest=plan_digest,
        iterations=iterations,
        current_state=current_state,
        learnings=learnings,
        followups=followups,
        code_delta=code_delta,
        step_shipping=step_shipping,
        risk_delta=risk_delta,
        report_md=report_md,
    )
