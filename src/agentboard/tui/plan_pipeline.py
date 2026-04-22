"""Plan pipeline widget — horizontal chain of the 5 gauntlet steps.

Renders as a one-line pipeline with drill-down via Enter. Wide layout
shows full step names; narrow (width ≤ 80) collapses to just `[icon]`
markers connected by `─`.

State model (6 states):

| Icon | State         | When it renders                                      |
|------|---------------|------------------------------------------------------|
| `·`  | PENDING       | Step artifact absent and no active signal in decisions |
| `◉`  | IN_PROGRESS   | Step artifact absent but the prior step shipped (implied active work) |
| `⟳`  | RETRYING      | Step artifact exists but was revised — design_review BLOCKER cleared, or explicit retry phase logged |
| `✓`  | PASSED        | Step artifact exists and no outstanding BLOCKER       |
| `✗`  | BLOCKED       | Last design_review verdict for the arch step is BLOCKER (not cleared) |
| `⊘`  | SKIPPED       | Step marked skipped via decisions metadata (rare)     |

Callers that don't have decisions fall back to the 2-state `✓`/`·` behavior
(file exists or not) — backward-compat with the legacy renderer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.widgets import Markdown as MarkdownWidget

STEPS: tuple[str, ...] = ("frame", "scope", "arch", "challenge", "decide")
STEP_LABELS: dict[str, str] = {
    "frame": "Frame",
    "scope": "Scope",
    "arch": "Arch",
    "challenge": "Challenge",
    "decide": "Decide",
}

# State icons — order follows the lifecycle.
STATE_PENDING = "·"
STATE_IN_PROGRESS = "◉"
STATE_RETRYING = "⟳"
STATE_PASSED = "✓"
STATE_BLOCKED = "✗"
STATE_SKIPPED = "⊘"


def _step_state(
    gauntlet_dir: Path,
    step: str,
    *,
    decisions: Iterable[dict] | None = None,
    prior_step_exists: bool = False,
) -> str:
    """Compute the state icon for a single gauntlet step.

    `decisions` is an iterable of decision-log rows; when None or empty the
    function falls back to the 2-state `✓`/`·` behavior (file exists or not)
    to preserve backward compatibility with existing callers + tests.
    """
    path = gauntlet_dir / f"{step}.md"
    try:
        file_exists = path.exists() and path.stat().st_size > 0
    except OSError:
        file_exists = False

    rows = list(decisions or [])

    # Decisions-driven refinement. Currently only the `arch` step has a
    # reliable decision signal (design_review BLOCKER / WARN / APPROVED).
    if step == "arch" and rows:
        dr_verdicts = [
            str(d.get("verdict_source", "")).upper()
            for d in rows
            if str(d.get("phase", "")) == "design_review"
        ]
        if dr_verdicts:
            last = dr_verdicts[-1]
            if last == "BLOCKER":
                return STATE_BLOCKED
            # BLOCKER was recorded at some point but the most recent verdict
            # is APPROVED / WARN — arch was revised, so surface that history.
            if "BLOCKER" in dr_verdicts:
                return STATE_RETRYING

    # File-existence baseline.
    if file_exists:
        return STATE_PASSED

    # IN_PROGRESS: step not yet written, but the prior step shipped, so work
    # is plausibly active on this one right now. Only applied when we have
    # decision data to anchor the inference; without it, stay PENDING to
    # match the legacy renderer.
    if rows and prior_step_exists:
        return STATE_IN_PROGRESS

    return STATE_PENDING


def render_pipeline(
    goal_dir: Path,
    narrow: bool = False,
    *,
    decisions: Iterable[dict] | None = None,
) -> str:
    """Render the 5-step pipeline as a single string.

    `goal_dir` is the goal directory (e.g. `.devboard/goals/<gid>/`).
    Gauntlet artifacts live under `goal_dir/gauntlet/*.md`.

    When `decisions` is provided, the renderer may emit IN_PROGRESS /
    RETRYING / BLOCKED icons in addition to the baseline PASSED / PENDING.
    When it is `None` (or empty), output matches the legacy 2-state
    behavior for test-fixture and pre-decisions-data compatibility.
    """
    gauntlet_dir = goal_dir / "gauntlet"
    rows = list(decisions or [])
    parts: list[str] = []
    prior_exists = False
    for step in STEPS:
        icon = _step_state(
            gauntlet_dir,
            step,
            decisions=rows,
            prior_step_exists=prior_exists,
        )
        if narrow:
            parts.append(f"[{icon}]")
        else:
            parts.append(f"[{icon} {STEP_LABELS[step]}]")
        # Track for next iteration — the IN_PROGRESS inference needs to
        # know whether the preceding step already shipped.
        prior_exists = icon in (STATE_PASSED, STATE_RETRYING)
    joiner = "─" if narrow else "──"
    return joiner.join(parts)


class PlanStepModal(ModalScreen[None]):
    """Full-screen modal showing one gauntlet step's markdown."""

    BINDINGS = [Binding("escape", "dismiss", "close", show=False)]

    def __init__(self, step_path: Path) -> None:
        super().__init__()
        self._step_path = step_path

    def compose(self):
        try:
            body = self._step_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            body = f"# {self._step_path.name}\n\n_(unreadable)_"
        yield MarkdownWidget(body, id="plan-step-modal-body")


class PlanPipeline(Static):
    """Plan tab pipeline widget. Enter opens the focused step's modal."""

    BINDINGS = [Binding("enter", "open_step", "drill", show=False)]

    def __init__(
        self,
        goal_dir: Path,
        narrow: bool = False,
        decisions: Iterable[dict] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._goal_dir = goal_dir
        self._narrow = narrow
        self._decisions: list[dict] = list(decisions or [])
        self._focused_step: str = STEPS[-1]  # default → last existing

    def refresh_render(
        self,
        goal_dir: Path | None = None,
        narrow: bool | None = None,
        decisions: Iterable[dict] | None = None,
    ) -> None:
        if goal_dir is not None:
            self._goal_dir = goal_dir
        if narrow is not None:
            self._narrow = narrow
        if decisions is not None:
            self._decisions = list(decisions)
        self.update(
            render_pipeline(self._goal_dir, self._narrow, decisions=self._decisions)
        )

    def on_mount(self) -> None:
        self.can_focus = True
        self.refresh_render()

    def action_open_step(self) -> None:
        step_path = self._goal_dir / "gauntlet" / f"{self._focused_step}.md"
        if self.app is not None:
            self.app.push_screen(PlanStepModal(step_path))
