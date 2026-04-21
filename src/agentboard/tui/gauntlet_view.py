from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


STEPS = ["Frame", "Scope", "Architecture", "Challenge", "Decide"]


class GauntletView(Widget):
    """5-step gauntlet progress indicator."""

    DEFAULT_CSS = """
    GauntletView {
        height: auto;
        border: solid $accent-darken-2;
        padding: 1 2;
    }
    GauntletView .gauntlet-title {
        text-style: bold;
        margin-bottom: 1;
    }
    GauntletView .step-row {
        height: 1;
    }
    """

    # -1 = not started, 0..4 = current step, 5 = done
    current_step: reactive[int] = reactive(-1)
    step_statuses: reactive[list[str]] = reactive(lambda: ["pending"] * 5)

    def compose(self) -> ComposeResult:
        yield Static("[bold]Planning Gauntlet[/bold]", classes="gauntlet-title", markup=True)
        for i, name in enumerate(STEPS):
            yield Static(self._step_line(i), id=f"step_{i}", classes="step-row", markup=True)

    def _step_line(self, i: int) -> str:
        status = self.step_statuses[i] if i < len(self.step_statuses) else "pending"
        icon = {"done": "[green]✓[/green]", "running": "[cyan]⟳[/cyan]", "pending": "[dim]○[/dim]"}.get(status, "?")
        name_str = f"[bold]{STEPS[i]}[/bold]" if status == "running" else STEPS[i]
        return f"  {icon} {name_str}"

    def _refresh_steps(self) -> None:
        for i in range(len(STEPS)):
            widget = self.query_one(f"#step_{i}", Static)
            widget.update(self._step_line(i))

    def set_step_running(self, step_idx: int) -> None:
        statuses = list(self.step_statuses)
        for j in range(len(statuses)):
            if j < step_idx:
                statuses[j] = "done"
            elif j == step_idx:
                statuses[j] = "running"
            else:
                statuses[j] = "pending"
        self.step_statuses = statuses
        self._refresh_steps()

    def set_step_done(self, step_idx: int) -> None:
        statuses = list(self.step_statuses)
        statuses[step_idx] = "done"
        self.step_statuses = statuses
        self._refresh_steps()

    def set_all_done(self) -> None:
        self.step_statuses = ["done"] * 5
        self._refresh_steps()

    def reset(self) -> None:
        self.step_statuses = ["pending"] * 5
        self._refresh_steps()
