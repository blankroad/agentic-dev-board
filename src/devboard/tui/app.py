from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer

from devboard.config import DevBoardConfig, load_config
from devboard.models import BoardState
from devboard.storage.file_store import FileStore
from devboard.tui.command_line import CommandLine
from devboard.tui.command_registry import (
    CommandRegistry,
    MissingArgError,
    UnknownCommandError,
)
from devboard.tui.commands import (
    decisions_cmd,
    diff_cmd,
    goals_cmd,
    goto_cmd,
    learn_cmd,
    runs_cmd,
)
from devboard.tui.context_viewer import ContextViewer
from devboard.tui.health_bar import HealthBar
from devboard.tui.live_stream_view import LiveStreamView
from devboard.tui.resources_view import ResourcesView


class DevBoardApp(App):
    """Three-pane glass cockpit for devboard v2.0.

    Layout: HealthBar / Horizontal(Resources | LiveStream | ContextViewer)
    / CommandLine / Footer. Read-only — writes go through MCP tools.
    """

    CSS = """
    Screen { layout: vertical; }
    #main-row { height: 1fr; }
    #live-stream { height: 3; border-top: solid $primary-darken-3; }
    #live-stream.expanded { height: 18; }
    #command-line { dock: bottom; height: 1; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("colon", "open_command_line", "Cmd"),
        Binding("1", "switch_tab('diff')", show=False),
        Binding("2", "switch_tab('decisions')", show=False),
        Binding("3", "switch_tab('learnings')", show=False),
        Binding("4", "switch_tab('gauntlet')", show=False),
        Binding("5", "switch_tab('plan')", show=False),
        Binding("right_square_bracket", "cycle_tab(1)", show=False),
        Binding("left_square_bracket", "cycle_tab(-1)", show=False),
        Binding("backslash", "toggle_livestream", "Toggle live stream"),
        Binding("question_mark", "help", "Help"),
    ]

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

    @property
    def board(self) -> BoardState:
        return self._board

    @property
    def store_root(self) -> Path:
        return self._store_root

    @property
    def store(self) -> FileStore:
        return self._store

    def compose(self) -> ComposeResult:
        yield HealthBar(id="health-bar")
        with Horizontal(id="main-row"):
            yield ResourcesView(id="resources")
            yield ContextViewer(id="context-viewer")
        yield LiveStreamView(id="live-stream")
        yield CommandLine(id="command-line", placeholder=":")
        yield Footer()

    def on_mount(self) -> None:
        for mod in (goals_cmd, runs_cmd, diff_cmd, decisions_cmd, goto_cmd, learn_cmd):
            mod.register(self)
        devboard_dir = self._store_root / ".devboard"
        if not devboard_dir.exists():
            self.query_one(LiveStreamView).set_empty_state(
                "No devboard state. Run `devboard init` and reopen."
            )
        else:
            self.query_one(LiveStreamView).set_empty_state(
                f"Ready — {len(self._board.goals)} goals. Type ':' for commands, '?' for help."
            )
        # Pre-populate Resources sidebar so users see content on launch
        # (spec required ':goals'/':runs' to populate on demand, but empty
        # sidebar on startup reads as broken). goals dispatched last so its
        # list is focused — which also moves focus off the CommandLine Input
        # so printable-key bindings (1-5, /, ?) fire.
        for cmd in ("runs", "goals"):
            try:
                self.commands.dispatch(cmd)
            except Exception:
                pass
        # Auto-load active goal's plan + gauntlet into the Context tabs
        try:
            self.query_one("#context-viewer", ContextViewer).load_active_goal_artifacts(
                self._store_root, self._board.active_goal_id
            )
        except Exception:
            pass
        # Wire tail worker to live-stream + health-bar via 100ms interval.
        from devboard.tui.tail_worker import RunTailWorker

        self._tail_worker = RunTailWorker(self, devboard_dir / "runs")
        self.set_interval(0.1, self._tail_worker.poll_once)

    def on_stream_event(self, text: str, color: str | None) -> None:
        """Main-thread callback invoked by RunTailWorker.poll_once for every
        new JSONL line. Adds the line to LiveStreamView and flashes HealthBar
        when the classifier found an anomaly."""
        self.query_one(LiveStreamView).append_line(text, color=color)
        if color:
            try:
                self.query_one(HealthBar).flash(color)
            except Exception:
                pass

    def action_open_command_line(self) -> None:
        cl = self.query_one("#command-line", CommandLine)
        cl.open(return_to=self.focused)

    def action_switch_tab(self, name: str) -> None:
        self.query_one("#context-viewer", ContextViewer).action_switch(name)

    def action_cycle_tab(self, step: int) -> None:
        self.query_one("#context-viewer", ContextViewer).action_cycle(step)

    def action_toggle_livestream(self) -> None:
        self.query_one("#live-stream", LiveStreamView).toggle_class("expanded")

    def action_help(self) -> None:
        from devboard.tui.help_modal import HelpModal

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
        cl.value = ""
        cl.styles.background = None

    def _show_error(self, cl: CommandLine, message: str) -> None:
        """Display a 1-second error hint. Later clears ONLY if the input
        still holds exactly this error string (red-team round 3 — stale
        timers must not wipe a user's subsequent typing)."""
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
