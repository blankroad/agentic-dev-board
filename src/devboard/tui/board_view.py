from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Label, Static

from devboard.models import BoardState, GoalStatus


STATUS_COLOR = {
    GoalStatus.active: "green",
    GoalStatus.converged: "blue",
    GoalStatus.awaiting_approval: "yellow",
    GoalStatus.pushed: "cyan",
    GoalStatus.blocked: "red",
    GoalStatus.archived: "dim",
}

STATUS_ICON = {
    GoalStatus.active: "●",
    GoalStatus.converged: "✓",
    GoalStatus.awaiting_approval: "?",
    GoalStatus.pushed: "↑",
    GoalStatus.blocked: "✗",
    GoalStatus.archived: "○",
}


class BoardView(Widget):
    """Kanban-style goal list with status and stats."""

    DEFAULT_CSS = """
    BoardView {
        height: 1fr;
    }
    BoardView #board-title {
        text-style: bold;
        padding: 0 1;
        background: $primary-darken-3;
    }
    BoardView DataTable {
        height: 1fr;
    }
    """

    def __init__(self, board: BoardState, store_root: Path, on_select: Callable[[str], None] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._board = board
        self._store_root = store_root
        self._on_select = on_select

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]Board[/bold]  [dim]{self._board.board_id[:16]}[/dim]", id="board-title", markup=True)
        table = DataTable(id="goal-table", cursor_type="row")
        yield table

    def on_mount(self) -> None:
        self._populate()

    def _populate(self) -> None:
        table = self.query_one("#goal-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Status", "Goal", "Tasks", "Plan", "ID")
        for goal in self._board.goals:
            color = STATUS_COLOR.get(goal.status, "white")
            icon = STATUS_ICON.get(goal.status, "?")
            has_plan = (self._store_root / ".devboard" / "goals" / goal.id / "plan.md").exists()
            table.add_row(
                f"[{color}]{icon} {goal.status.value}[/{color}]",
                goal.title[:50],
                str(len(goal.task_ids)),
                "[green]✓[/green]" if has_plan else "[dim]—[/dim]",
                goal.id[:20],
                key=goal.id,
            )

    def refresh_board(self, board: BoardState) -> None:
        self._board = board
        self._populate()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        goal_id = str(event.row_key.value)
        if self._on_select:
            self._on_select(goal_id)
