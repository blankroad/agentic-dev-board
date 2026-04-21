from __future__ import annotations

import threading
from pathlib import Path

from rich.console import Console
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, RichLog, Static, TabbedContent, TabPane

from agentboard.config import DevBoardConfig, load_config
from agentboard.models import BoardState, GoalStatus
from agentboard.storage.file_store import FileStore
from agentboard.tui.board_view import BoardView
from agentboard.tui.gauntlet_view import GauntletView
from agentboard.tui.log_view import LogView
from agentboard.tui.task_view import TaskView


class DevBoardApp(App):
    """Autonomous LLM Dev Board — Textual TUI."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-tabs {
        height: 1fr;
    }
    #board-pane {
        layout: horizontal;
        height: 1fr;
    }
    #left-panel {
        width: 60%;
        height: 1fr;
        layout: vertical;
    }
    #right-panel {
        width: 40%;
        height: 1fr;
        layout: vertical;
        border-left: solid $primary-darken-3;
    }
    #status-bar {
        height: 1;
        background: $primary-darken-3;
        padding: 0 1;
        color: $text-muted;
    }
    #log-pane {
        height: 1fr;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+r", "refresh_board", "Refresh"),
        Binding("ctrl+p", "pause_loop", "Pause", show=False),
        Binding("ctrl+i", "inject_hint", "Hint", show=False),
        Binding("f1", "switch_tab('board')", "Board"),
        Binding("f2", "switch_tab('log')", "Log"),
    ]

    selected_goal_id: reactive[str | None] = reactive(None)
    status_text: reactive[str] = reactive("Ready")

    def __init__(self, store_root: Path) -> None:
        super().__init__()
        self._store_root = store_root
        self._store = FileStore(store_root)
        self._config = load_config(store_root)
        self._board = self._store.load_board()
        self._paused = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs", initial="board"):
            with TabPane("Board [F1]", id="board"):
                with Horizontal(id="board-pane"):
                    with Vertical(id="left-panel"):
                        yield BoardView(
                            board=self._board,
                            store_root=self._store_root,
                            on_select=self._on_goal_selected,
                            id="board-view",
                        )
                    with Vertical(id="right-panel"):
                        yield GauntletView(id="gauntlet-view")
                        yield TaskView(id="task-view")
            with TabPane("Log [F2]", id="log"):
                yield LogView(id="log-view")
        yield Static(self.status_text, id="status-bar", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._update_status("Ready — select a goal and press Enter")

    # ── Goal selection ────────────────────────────────────────────────────────

    def _on_goal_selected(self, goal_id: str) -> None:
        self.selected_goal_id = goal_id
        self._load_goal_detail(goal_id)

    def _load_goal_detail(self, goal_id: str) -> None:
        board = self._store.load_board()
        goal = board.get_goal(goal_id)
        if not goal:
            return

        plan = self._store.load_locked_plan(goal_id)
        task_view = self.query_one("#task-view", TaskView)
        task_view.show_goal(goal_id, goal.title, plan)
        task_view.clear_iterations()

        # Load decision log if tasks exist
        for task_id in goal.task_ids:
            entries = self._store.load_decisions(task_id)
            for entry in entries:
                if entry.phase == "review":
                    task_view.add_iteration(
                        entry.iter,
                        verdict=entry.verdict_source,
                        plan_preview=entry.reasoning[:40],
                        test_preview="",
                    )

        # Gauntlet steps
        gauntlet = self.query_one("#gauntlet-view", GauntletView)
        step_names = ["frame", "scope", "arch", "challenge", "decide"]
        done = sum(
            1 for s in step_names
            if (self._store_root / ".devboard" / "goals" / goal_id / "gauntlet" / f"{s}.md").exists()
        )
        if done == 5:
            gauntlet.set_all_done()
        elif done > 0:
            gauntlet.set_step_running(done)
        else:
            gauntlet.reset()

        if goal.status == GoalStatus.converged:
            task_view.mark_converged()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh_board(self) -> None:
        self._board = self._store.load_board()
        board_view = self.query_one("#board-view", BoardView)
        board_view.refresh_board(self._board)
        self._update_status("Board refreshed")

    def action_pause_loop(self) -> None:
        self._paused = not self._paused
        state = "PAUSED" if self._paused else "RUNNING"
        self._update_status(f"Loop {state}")

    def action_inject_hint(self) -> None:
        from agentboard.orchestrator.interrupt import get_hint_queue
        from textual.widgets import Input
        # Use notify as lightweight prompt — full modal is Phase F TUI polish
        hq = get_hint_queue()
        if hq.is_paused:
            hq.resume()
            self._update_status("Loop resumed")
        else:
            hq.pause()
            self._update_status("Loop paused — type hint in log tab, then Ctrl+I to resume")

    def action_switch_tab(self, tab: str) -> None:
        self.query_one("#main-tabs", TabbedContent).active = tab

    # ── Status bar ────────────────────────────────────────────────────────────

    def _update_status(self, msg: str) -> None:
        self.status_text = msg
        self.query_one("#status-bar", Static).update(f"[dim]{msg}[/dim]")

    # ── Public API for external loop progress updates ─────────────────────────

    def log_step(self, step: str, detail: str = "") -> None:
        """Called from background thread — safe update."""
        self.call_from_thread(self._do_log_step, step, detail)

    def _do_log_step(self, step: str, detail: str) -> None:
        self.query_one("#log-view", LogView).write_step(step, detail)

    def log_verdict(self, verdict: str, iteration: int) -> None:
        self.call_from_thread(self._do_log_verdict, verdict, iteration)

    def _do_log_verdict(self, verdict: str, iteration: int) -> None:
        self.query_one("#log-view", LogView).write_verdict(verdict, iteration)
        self._update_status(f"Iteration {iteration}: {verdict}")

    def log_tool(self, tool_name: str, result: str, error: bool = False) -> None:
        self.call_from_thread(self._do_log_tool, tool_name, result, error)

    def _do_log_tool(self, tool_name: str, result: str, error: bool) -> None:
        self.query_one("#log-view", LogView).write_tool(tool_name, result, error)

    def set_gauntlet_step(self, step_idx: int, done: bool = False) -> None:
        self.call_from_thread(self._do_gauntlet_step, step_idx, done)

    def _do_gauntlet_step(self, step_idx: int, done: bool) -> None:
        gv = self.query_one("#gauntlet-view", GauntletView)
        if done:
            gv.set_step_done(step_idx)
        else:
            gv.set_step_running(step_idx)

    def notify_converged(self, goal_id: str, iterations: int) -> None:
        self.call_from_thread(self._do_notify_converged, goal_id, iterations)

    def _do_notify_converged(self, goal_id: str, iterations: int) -> None:
        self._load_goal_detail(goal_id)
        self.action_refresh_board()
        self._update_status(f"✓ Converged in {iterations} iteration(s) — awaiting approval")
        self.notify(f"Goal converged in {iterations} iteration(s)!", title="agentboard", severity="information")


def run_tui(store_root: Path) -> None:
    """Launch the TUI. Blocks until user quits."""
    app = DevBoardApp(store_root=store_root)
    app.run()
