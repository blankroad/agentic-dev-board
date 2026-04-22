from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, RichLog, Static

from agentboard.models import LockedPlan


class TaskView(Widget):
    """Detail panel: locked plan checklist + iteration history for selected goal."""

    DEFAULT_CSS = """
    TaskView {
        height: 1fr;
        layout: vertical;
    }
    TaskView #task-title {
        text-style: bold;
        padding: 0 1;
        background: $surface;
    }
    TaskView #checklist {
        height: auto;
        max-height: 12;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    TaskView #iter-table {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[dim]Select a goal from the board[/dim]", id="task-title", markup=True)
        yield Static("", id="checklist", markup=True)
        table = DataTable(id="iter-table", cursor_type="row")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#iter-table", DataTable)
        table.add_columns("Iter", "Verdict", "Plan", "Tests")

    def show_goal(self, goal_id: str, goal_title: str, plan: LockedPlan | None, decisions_path=None) -> None:
        self.query_one("#task-title", Static).update(
            f"[bold]{goal_title}[/bold]  [dim]{goal_id[:20]}[/dim]"
        )
        checklist_widget = self.query_one("#checklist", Static)
        if plan:
            lines = [f"[bold]Checklist[/bold] ({len(plan.goal_checklist)} items)"]
            for item in plan.goal_checklist:
                lines.append(f"  [dim]☐[/dim] {item}")
            checklist_widget.update("\n".join(lines))
        else:
            checklist_widget.update("[dim]No locked plan yet — run: agentboard goal plan[/dim]")

    def add_iteration(self, n: int, verdict: str, plan_preview: str, test_preview: str) -> None:
        table = self.query_one("#iter-table", DataTable)
        colors = {"PASS": "green", "RETRY": "yellow", "REPLAN": "red"}
        color = colors.get(verdict, "white")
        table.add_row(
            str(n),
            f"[{color}]{verdict}[/{color}]",
            plan_preview[:40],
            test_preview[:30],
        )

    def clear_iterations(self) -> None:
        table = self.query_one("#iter-table", DataTable)
        table.clear()

    def mark_converged(self) -> None:
        self.query_one("#task-title", Static).update(
            self.query_one("#task-title", Static).renderable  # type: ignore
        )
        # Append converged indicator
        title = self.query_one("#task-title", Static)
        title.update(str(title.renderable) + "  [bold green][CONVERGED][/bold green]")
