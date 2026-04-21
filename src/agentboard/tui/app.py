from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer

from agentboard.config import DevBoardConfig, load_config
from agentboard.models import BoardState
from agentboard.storage.file_store import FileStore
from agentboard.tui.activity_row import ActivityRow
from agentboard.tui.command_line import CommandLine
from agentboard.tui.command_registry import (
    CommandRegistry,
    MissingArgError,
    UnknownCommandError,
)
from agentboard.tui.commands import (
    decisions_cmd,
    diff_cmd,
    goals_cmd,
    goto_cmd,
    learn_cmd,
    runs_cmd,
)
from agentboard.tui.goal_side_list import GoalSideList  # noqa: F401 used via message
from agentboard.tui.live_status_line import LiveStatusLine
from agentboard.tui.phase_flow import PhaseFlowView
from agentboard.tui.session_derive import SessionContext
from agentboard.tui.status_bar import StatusBar


class DevBoardApp(App):
    """v2.3 phase-flow cockpit (right column removed).

    Layout:
      StatusBar (1 line)
      Horizontal(GoalSideList 15% | PhaseFlowView 1fr)
      LiveStatusLine (1 line)
      CommandLine (dock bottom, 1 line)
      Footer

    The center column is a 5-tab PhaseFlowView (Overview / Plan / Dev /
    Result / Review) whose tab bodies are wrapped in VerticalScroll so
    ↓/PgDn/wheel scroll overflowing content. Number keys 1/2/3/4/5 jump
    between tabs; ctrl+p pins the view so live phase-auto-switch does
    not yank the current tab.

    Read-only — writes go through MCP tools. v2.0 commands (:goto/:diff/
    :decisions/:learn/:goals/:runs) still dispatch for backward compat.
    """

    CSS = """
    Screen { layout: vertical; }
    #main-row { height: 1fr; }
    #center-col { width: 1fr; }
    #command-line { dock: bottom; height: 1; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("colon", "open_command_line", "Cmd"),
        Binding("question_mark", "help", "Help"),
        Binding("ctrl+p", "toggle_phase_flow_pin", "Pin", show=False, priority=True),
        # 1/2/3/4 must be App-level: on boot, focus is on #resources-goals
        # (ListView) and widget-level priority bindings on PhaseFlowView
        # do not fire for character keys from that focus. App-level
        # bindings are the only reliable path.
        Binding("1", "phase_flow_tab('overview')", "Overview", show=False, priority=True),
        Binding("2", "phase_flow_tab('plan')", "Plan", show=False, priority=True),
        Binding("3", "phase_flow_tab('dev')", "Dev", show=False, priority=True),
        Binding("4", "phase_flow_tab('result')", "Result", show=False, priority=True),
        Binding("5", "phase_flow_tab('review')", "Review", show=False, priority=True),
    ]

    selected_iter: reactive[int | None] = reactive(None)

    def __init__(self, store_root: Path) -> None:
        super().__init__()
        self._store_root = store_root
        self._store = FileStore(store_root)
        try:
            self._board: BoardState = self._store.load_board()
        except Exception:
            self._board = BoardState()
        try:
            self._config: DevBoardConfig = load_config(store_root)
        except Exception:
            self._config = DevBoardConfig()
        self.commands = CommandRegistry()
        self._session = SessionContext(store_root)
        self._task_id: str | None = self._pick_task_id()

    @property
    def board(self) -> BoardState:
        return self._board

    @property
    def store_root(self) -> Path:
        return self._store_root

    @property
    def store(self) -> FileStore:
        return self._store

    @property
    def session(self) -> SessionContext:
        return self._session

    def _pick_task_id(self) -> str | None:
        gid = self._session.active_goal_id
        if not gid:
            return None
        tasks_dir = self._store_root / ".devboard" / "goals" / gid / "tasks"
        if not tasks_dir.exists():
            return None
        dirs = [p for p in tasks_dir.iterdir() if p.is_dir()]
        if not dirs:
            return None
        latest = max(dirs, key=lambda p: p.stat().st_mtime)
        return latest.name

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status-bar")
        with Horizontal(id="main-row"):
            yield GoalSideList(self._session, id="goal-side-list")
            with Vertical(id="center-col"):
                yield PhaseFlowView(
                    self._session, task_id=self._task_id, id="phase-flow"
                )
        yield LiveStatusLine(id="live-status-line")
        yield CommandLine(id="command-line", placeholder=":")
        yield Footer()

    def _initial_iter(self) -> int | None:
        if not self._task_id:
            return None
        rows = self._session.decisions_for_task(self._task_id)
        return rows[0].get("iter") if rows else None

    def on_mount(self) -> None:
        for mod in (goals_cmd, runs_cmd, diff_cmd, decisions_cmd, goto_cmd, learn_cmd):
            mod.register(self)
        # initialize selected_iter AFTER mount so the watcher fires normally
        self.selected_iter = self._initial_iter()
        # set initial StatusBar summary
        self._refresh_status_bar()
        # Focus the center tab's VerticalScroll so ↓/PgDn/wheel scroll
        # overflowing content without the user having to click first
        # (redteam CRITICAL: ListView in #resources-goals would otherwise
        # consume arrow keys). PhaseFlowView.focus_active_tab_scroll
        # falls back silently if the scroll container isn't mounted yet.
        try:
            self.query_one("#phase-flow", PhaseFlowView).focus_active_tab_scroll()
        except Exception:
            pass
        # wire tail worker for live updates (throttled single-line StatusBar only)
        devboard_dir = self._store_root / ".devboard"
        if devboard_dir.exists():
            from agentboard.tui.tail_worker import RunTailWorker

            self._tail_worker = RunTailWorker(self, devboard_dir / "runs")
            self.set_interval(0.1, self._tail_worker.poll_once)

    def on_stream_event(self, text: str, color: str | None) -> None:
        """RunTailWorker callback. Updates:
        (a) StatusBar — active-goal curated segments (selected_iter context)
        (b) LiveStatusLine — raw tail feed of the latest event at bottom
        (c) PhaseFlowView — mtime-gated phase auto-switch via handle_tick"""
        self._refresh_status_bar(latest_line=text)
        try:
            self.query_one("#live-status-line", LiveStatusLine).set_line(text, color)
        except Exception:
            pass
        try:
            self.query_one("#phase-flow", PhaseFlowView).handle_tick()
        except Exception:
            pass

    def _refresh_status_bar(self, latest_line: str | None = None) -> None:
        try:
            sb = self.query_one("#status-bar", StatusBar)
        except Exception:
            return
        gid = self._session.active_goal_id
        title = ""
        if gid:
            for g in self._session.all_goals():
                if g.get("id") == gid:
                    title = str(g.get("title", gid))
                    break
        iter_n = self.selected_iter
        phase = ""
        redteam = ""
        tests: int | None = None
        if self._task_id:
            decisions = self._session.decisions_for_task(self._task_id)
            if iter_n is not None:
                for d in decisions:
                    if d.get("iter") == iter_n:
                        phase = str(d.get("phase", ""))
                        break
            for d in decisions:
                if d.get("phase") == "redteam":
                    redteam = str(d.get("verdict_source", ""))
                    break
        sb.set_segments(
            goal_title=title, iter_n=iter_n, phase=phase, redteam=redteam, tests=tests
        )

    def refresh_for_active_goal(self) -> None:
        """Re-render every pane that depends on session.active_goal_id.
        Called by command handlers (e.g. :goto) after mutating state."""
        self._task_id = self._pick_task_id()
        self.selected_iter = self._initial_iter()
        try:
            flow = self.query_one("#phase-flow", PhaseFlowView)
            flow.refresh_content(task_id=self._task_id)
        except Exception:
            pass
        try:
            self.query_one("#goal-side-list").refresh_content()
        except Exception:
            pass
        self._refresh_status_bar()

    def refresh_for_active_task(self) -> None:
        """Re-render PhaseFlowView for a task switch (without changing
        active goal). Called by :decisions."""
        try:
            flow = self.query_one("#phase-flow", PhaseFlowView)
            flow.refresh_content(task_id=self._task_id)
        except Exception:
            pass
        self._refresh_status_bar()

    def watch_selected_iter(self, _old: int | None, _new: int | None) -> None:
        self._refresh_status_bar()

    def action_open_command_line(self) -> None:
        cl = self.query_one("#command-line", CommandLine)
        cl.open(return_to=self.focused)

    def action_toggle_phase_flow_pin(self) -> None:
        try:
            self.query_one("#phase-flow", PhaseFlowView).action_toggle_pin()
        except Exception:
            pass

    def action_phase_flow_tab(self, tab_id: str) -> None:
        try:
            self.query_one("#phase-flow", PhaseFlowView).action_activate_tab(tab_id)
        except Exception:
            pass

    def on_status_bar_clicked(self, _event: StatusBar.Clicked) -> None:
        pass

    def on_goal_side_list_goal_selected(
        self, event: GoalSideList.GoalSelected
    ) -> None:
        """Click/Enter on a sidebar goal → equivalent of ':goto <gid>'."""
        try:
            self.commands.dispatch(f"goto {event.goal_id}")
        except Exception:
            pass

    def on_activity_row_selected(self, event: ActivityRow.Selected) -> None:
        """Click or Enter on a timeline row → update selected_iter so the
        StatusBar watcher refreshes to that iter's phase/verdict."""
        iter_n = event.entry.get("iter")
        if isinstance(iter_n, int):
            self.selected_iter = iter_n

    def action_help(self) -> None:
        from agentboard.tui.help_modal import HelpModal

        self.push_screen(HelpModal())

    def on_input_submitted(self, event) -> None:
        if event.input.id != "command-line":
            return
        raw = event.value
        cl = event.input
        try:
            self.commands.dispatch(raw)
        except (UnknownCommandError, MissingArgError) as err:
            self._show_error(cl, str(err))
            return
        except Exception as exc:  # noqa: BLE001 — handler surface must not crash App
            self._show_error(cl, f"Error: {exc}")
            return
        # Only clear the input if the handler didn't write a hint/result.
        # Commands like :goto ambiguous / :runs / :diff leave a success
        # message in cl.value that the user should see.
        if cl.value == raw:
            cl.value = ""
            cl.styles.background = None

    def _show_error(self, cl: CommandLine, message: str) -> None:
        cl.styles.background = "red"
        cl.value = message

        def _clear_if_stale() -> None:
            if cl.value == message:
                cl.value = ""
                cl.styles.background = None

        self.set_timer(1.0, _clear_if_stale)


def run_tui(store_root: Path) -> None:
    app = DevBoardApp(store_root=store_root)
    app.run()
