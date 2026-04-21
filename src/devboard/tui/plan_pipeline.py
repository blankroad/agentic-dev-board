"""Plan pipeline widget — horizontal [✓/·] chain of the 5 gauntlet steps.

Renders as a one-line pipeline with drill-down via Enter. Wide layout
shows full step names; narrow (width ≤ 80) collapses to just `[icon]`
markers connected by `─`.
"""

from __future__ import annotations

from pathlib import Path

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


def _step_state(gauntlet_dir: Path, step: str) -> str:
    """Return ✓ if the step markdown exists with content, · otherwise."""
    path = gauntlet_dir / f"{step}.md"
    try:
        if path.exists() and path.stat().st_size > 0:
            return "✓"
    except OSError:
        pass
    return "·"


def render_pipeline(goal_dir: Path, narrow: bool = False) -> str:
    """Render the 5-step pipeline as a single string.

    goal_dir is the goal directory (e.g. `.devboard/goals/<gid>/`).
    Gauntlet artifacts live under goal_dir/gauntlet/*.md.
    """
    gauntlet_dir = goal_dir / "gauntlet"
    parts: list[str] = []
    for step in STEPS:
        icon = _step_state(gauntlet_dir, step)
        if narrow:
            parts.append(f"[{icon}]")
        else:
            parts.append(f"[{icon} {STEP_LABELS[step]}]")
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

    def __init__(self, goal_dir: Path, narrow: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._goal_dir = goal_dir
        self._narrow = narrow
        self._focused_step: str = STEPS[-1]  # default → last existing

    def refresh_render(self, goal_dir: Path | None = None, narrow: bool | None = None) -> None:
        if goal_dir is not None:
            self._goal_dir = goal_dir
        if narrow is not None:
            self._narrow = narrow
        self.update(render_pipeline(self._goal_dir, self._narrow))

    def on_mount(self) -> None:
        self.can_focus = True
        self.refresh_render()

    def action_open_step(self) -> None:
        step_path = self._goal_dir / "gauntlet" / f"{self._focused_step}.md"
        if self.app is not None:
            self.app.push_screen(PlanStepModal(step_path))
