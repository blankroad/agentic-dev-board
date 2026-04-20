"""PhaseFlowView — center-panel 4-tab TabbedContent.

Replaces legacy PlanMarkdown + ActivityTimeline with a lifecycle-oriented
view: Plan / Dev / Result / Review. Each tab is driven by its own data
source through SessionContext.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane

from devboard.tui.session_derive import SessionContext


_EMPTY_PLAN = "_Plan not locked. Run `devboard-gauntlet`._"

# Dev-phase classifier: exact set + prefix set.
# Real log_decision writes phases like tdd_red/tdd_green/tdd_refactor, so
# we prefix-match 'tdd_' in addition to exact-matching pure tokens.
_DEV_PHASE_EXACT: frozenset[str] = frozenset({"dev", "eng_review", "iron_law", "rca"})
_DEV_PHASE_PREFIX: tuple[str, ...] = ("tdd_", "tdd")

_REVIEW_PHASE_EXACT: frozenset[str] = frozenset(
    # 'review' (not 'reviewer') is the canonical phase string used in
    # decisions.jsonl across orchestrator/graph.py, analytics/*, narrative/
    # generator.py, and cli.py. Keep this set in sync with those writers.
    {"review", "cso", "redteam", "parallel_review", "approval"}
)

# Manual override: when user switches tab via number key, suppress auto-
# switch for this many seconds so an incoming decision doesn't yank focus.
_MANUAL_OVERRIDE_SECONDS: float = 10.0

# Per LockedPlan borderlines: approval → Result tab; review-cluster → Review.
# Dev-cluster → Dev. Unknown phases → no-op (current tab preserved).
PHASE_TO_TAB: dict[str, str] = {
    # Plan — gauntlet 5-step + adjacent planning phases.
    "gauntlet": "plan",
    "frame": "plan",
    "scope": "plan",
    "arch": "plan",
    "challenge": "plan",
    "decide": "plan",
    "brainstorm": "plan",
    "plan": "plan",
    # Dev — TDD + engineering-review + root-cause loops.
    "dev": "dev",
    "eng_review": "dev",
    "iron_law": "dev",
    "rca": "dev",
    # Review — the canonical phase is 'review' (not 'reviewer').
    "review": "review",
    "cso": "review",
    "redteam": "review",
    "parallel_review": "review",
    # Result — final approval step lands here (borderline: approval→Result).
    "approval": "result",
}


def _phase_to_tab(phase: str) -> str | None:
    """Resolve phase → tab id. tdd_* prefix collapses to 'dev'."""
    if phase in PHASE_TO_TAB:
        return PHASE_TO_TAB[phase]
    if phase.startswith("tdd"):
        return "dev"
    return None


def _is_dev_phase(phase: str) -> bool:
    if phase in _DEV_PHASE_EXACT:
        return True
    return any(phase.startswith(p) for p in _DEV_PHASE_PREFIX)


def _is_review_phase(phase: str) -> bool:
    return phase in _REVIEW_PHASE_EXACT


def _safe_read(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return fallback


def _read_last_decision(path: Path) -> dict | None:
    """Return the last non-empty JSON object line from decisions.jsonl.

    Chosen over session.decisions_for_task()[0] so that a replay that
    appends a row with an older iter still drives the tab switch.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in reversed(text.splitlines()):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            return entry
    return None


_TAB_IDS: tuple[str, ...] = ("plan", "dev", "result", "review")


class PhaseFlowView(Widget):
    """4-tab center panel: Plan / Dev / Result / Review."""

    DEFAULT_CSS = """
    PhaseFlowView { height: 1fr; }
    """

    BINDINGS = [
        Binding("1", "activate_tab('plan')", "Plan", show=False, priority=True),
        Binding("2", "activate_tab('dev')", "Dev", show=False, priority=True),
        Binding("3", "activate_tab('result')", "Result", show=False, priority=True),
        Binding("4", "activate_tab('review')", "Review", show=False, priority=True),
    ]

    can_focus = True

    pinned: reactive[bool] = reactive(False)

    def __init__(
        self,
        session: SessionContext,
        task_id: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._task_id = task_id
        self.manual_override_until: float | None = None

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="plan"):
            with TabPane("Plan", id="plan"):
                # Rich Markdown wrap so plan_summary.md renders with
                # proper headings / lists in the TUI, and matches the
                # legacy PlanMarkdown contract expected by
                # tests/test_plan_markdown_narrative_scroll.py.
                yield Static(Markdown(self._load_plan_body()), id="plan-body")
            with TabPane("Dev", id="dev"):
                yield Static(self._load_dev_body(), id="dev-body", markup=False)
            with TabPane("Result", id="result"):
                yield Static(self._load_result_body(), id="result-body", markup=False)
            with TabPane("Review", id="review"):
                yield Static(self._load_review_body(), id="review-body", markup=False)

    def _load_plan_body(self) -> str:
        gid = self._session.active_goal_id
        if not gid:
            return _EMPTY_PLAN
        goal_dir = self._session.store_root / ".devboard" / "goals" / gid
        summary = goal_dir / "plan_summary.md"
        if summary.exists():
            return _safe_read(summary, _EMPTY_PLAN)
        plan = goal_dir / "plan.md"
        if plan.exists():
            return _safe_read(plan, _EMPTY_PLAN)
        return _EMPTY_PLAN

    def plan_body_text(self) -> str:
        try:
            content = self.query_one("#plan-body", Static).content
        except Exception:
            return ""
        # Static.content wraps the renderable; when given a rich.Markdown
        # the Text conversion drops the source, so prefer the Markdown's
        # markup attribute when available.
        markup = getattr(content, "markup", None)
        if isinstance(markup, str):
            return markup
        return str(content)

    def _load_dev_body(self) -> str:
        if not self._task_id:
            return ""
        rows = self._session.decisions_for_task(self._task_id)
        lines: list[str] = []
        for r in rows:
            if _is_dev_phase(str(r.get("phase", ""))):
                lines.append(
                    f"iter {r.get('iter', '?')}  {r.get('phase', '?')}  "
                    f"{r.get('verdict_source', '')}"
                )
        return "\n".join(lines)

    def dev_body_text(self) -> str:
        try:
            content = self.query_one("#dev-body", Static).content
        except Exception:
            return ""
        return str(content)

    def _load_result_body(self) -> str:
        gid = self._session.active_goal_id
        if not gid:
            return ""
        plan_json = (
            self._session.store_root / ".devboard" / "goals" / gid / "plan.json"
        )
        if not plan_json.exists():
            return ""
        try:
            data = json.loads(plan_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return ""
        steps = data.get("atomic_steps", [])
        total = 0
        done = 0
        lines: list[str] = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            total += 1
            completed = bool(s.get("completed"))
            if completed:
                done += 1
            mark = "[x]" if completed else "[ ]"
            lines.append(
                f"{mark} {s.get('id', '?')}  {s.get('behavior', '')}"
            )
        header = f"[{done}/{total} done]"
        return header + "\n" + "\n".join(lines) if lines else header

    def result_body_text(self) -> str:
        try:
            content = self.query_one("#result-body", Static).content
        except Exception:
            return ""
        return str(content)

    def _load_review_body(self) -> str:
        if not self._task_id:
            return ""
        rows = self._session.decisions_for_task(self._task_id)
        lines: list[str] = []
        for r in rows:
            if _is_review_phase(str(r.get("phase", ""))):
                lines.append(
                    f"iter {r.get('iter', '?')}  {r.get('phase', '?')}  "
                    f"{r.get('verdict_source', '')}"
                )
        return "\n".join(lines)

    def review_body_text(self) -> str:
        try:
            content = self.query_one("#review-body", Static).content
        except Exception:
            return ""
        return str(content)

    # ----- Badges -----

    def _dev_count(self) -> int:
        if not self._task_id:
            return 0
        rows = self._session.decisions_for_task(self._task_id)
        return sum(1 for r in rows if _is_dev_phase(str(r.get("phase", ""))))

    def _atomic_steps_total(self) -> int:
        gid = self._session.active_goal_id
        if not gid:
            return 0
        plan_json = (
            self._session.store_root / ".devboard" / "goals" / gid / "plan.json"
        )
        if not plan_json.exists():
            return 0
        try:
            data = json.loads(plan_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return 0
        steps = data.get("atomic_steps", [])
        return sum(1 for s in steps if isinstance(s, dict))

    def _dev_badge(self) -> str:
        return f"Dev {self._dev_count()}/{self._atomic_steps_total()}"

    def refresh_badges(self) -> None:
        """Recompute and apply dynamic tab labels (Dev N/M for now)."""
        try:
            tc = self.query_one(TabbedContent)
            tc.get_tab("dev").label = self._dev_badge()
        except Exception:
            return

    def refresh_content(self, task_id: str | None = ...) -> None:  # type: ignore[assignment]
        """Re-read active goal / task data and push into each tab body.

        Called by DevBoardApp after :goto or :decisions mutates state.
        Leaves TabbedContent.active untouched — user's current view wins
        unless auto-switch fires separately via handle_new_decision.
        """
        if task_id is not ...:
            self._task_id = task_id
        try:
            self.query_one("#plan-body", Static).update(Markdown(self._load_plan_body()))
        except Exception:
            pass
        try:
            self.query_one("#dev-body", Static).update(self._load_dev_body())
        except Exception:
            pass
        try:
            self.query_one("#result-body", Static).update(self._load_result_body())
        except Exception:
            pass
        try:
            self.query_one("#review-body", Static).update(self._load_review_body())
        except Exception:
            pass
        self.refresh_badges()

    def dev_badge_text(self) -> str:
        try:
            tc = self.query_one(TabbedContent)
            return str(tc.get_tab("dev").label)
        except Exception:
            return ""

    def action_activate_tab(self, tab_id: str) -> None:
        if tab_id not in _TAB_IDS:
            return
        try:
            tc = self.query_one(TabbedContent)
        except Exception:
            return
        tc.active = tab_id
        # Manual key press establishes a temporary window during which
        # auto-switch is suppressed. handle_new_decision checks this.
        self.manual_override_until = time.monotonic() + _MANUAL_OVERRIDE_SECONDS

    def action_toggle_pin(self) -> None:
        self.pinned = not self.pinned

    def handle_tick(self) -> None:
        """Called on every RunTailWorker tick.

        mtime-gates a re-read of decisions.jsonl; on change, dispatches
        the most-recently-appended row (the last non-empty line on disk —
        NOT the max-iter row, which can be stale during devboard-replay
        where newer writes have lower iter) to handle_new_decision.
        Honors pin + manual-override. Also refreshes badges.
        """
        if not self._task_id:
            return
        gid = self._session.active_goal_id
        if not gid:
            return
        decisions_path = (
            self._session.store_root
            / ".devboard"
            / "goals"
            / gid
            / "tasks"
            / self._task_id
            / "decisions.jsonl"
        )
        try:
            mtime = decisions_path.stat().st_mtime if decisions_path.exists() else None
        except OSError:
            return
        if mtime is None:
            return
        if getattr(self, "_last_decisions_mtime", None) == mtime:
            return
        self._last_decisions_mtime = mtime
        latest = _read_last_decision(decisions_path)
        if latest is not None:
            self.handle_new_decision(latest)
        self.refresh_badges()

    def handle_new_decision(self, decision: dict) -> None:
        """Called when a fresh decisions.jsonl row is observed.

        Routes to the matching tab via PHASE_TO_TAB unless pin is on or
        the user recently pressed a number key (manual override window).
        """
        if self.pinned:
            return
        if (
            self.manual_override_until is not None
            and time.monotonic() < self.manual_override_until
        ):
            return
        phase = str(decision.get("phase", ""))
        target = _phase_to_tab(phase)
        if target is None:
            return
        # Auto-switch must not re-arm the manual-override window.
        try:
            tc = self.query_one(TabbedContent)
        except Exception:
            return
        tc.active = target
