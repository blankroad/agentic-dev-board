"""FleetScreen — pushable Textual Screen, k9s-style cockpit
(M2-fleet-tui s_006, s_009).

Composition: Horizontal(FleetListPane | FleetEventStream).
Keybindings: ↓/↑ (delegate to FleetListPane), Enter (activate+pop),
            q (pop), / (open filter), r (replay), k (kill).
Mount: load_fleet(store) → pane.set_rows, start RunTailWorker polling,
       explicit focus on FleetListPane to neutralize default-focus bug.
Unmount: stop tail-worker interval so poll does not leak post-pop.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Input, Static

from agentboard.analytics.fleet_aggregator import load_fleet
from agentboard.tui.fleet_event_stream import FleetEventStream
from agentboard.tui.fleet_view import FleetListPane

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore
    from agentboard.tui.session_derive import SessionContext


@dataclass
class GoalActivated(Message):
    """Posted when user hits Enter on a FleetListPane row."""

    goal_id: str


class FleetScreen(Screen):
    """k9s-style fleet cockpit. Push via AgentBoardApp 'F' binding."""

    CSS = """
    FleetScreen { layout: vertical; }
    #fleet-main { height: 1fr; }
    #fleet-list-col { width: 2fr; }
    #fleet-stream-col { width: 1fr; }
    #fleet-filter { dock: bottom; height: 1; display: none; }
    #fleet-filter.-open { display: block; }
    """

    BINDINGS = [
        Binding("q", "pop_screen_fleet", "Back"),
        Binding("enter", "activate_selected", "Open", priority=True),
        Binding("slash", "open_filter", "Filter"),
        Binding("r", "replay_selected", "Replay"),
        Binding("k", "kill_selected", "Kill"),
        Binding("y", "confirm_kill", "Confirm", show=False, priority=True),
        Binding("escape", "dismiss_filter", "Cancel", show=False, priority=True),
    ]

    def __init__(
        self,
        store: "FileStore",
        session: "SessionContext",
        store_root: Path,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._store = store
        self._session = session
        self._store_root = store_root
        self._tail_timer = None
        self._tail_worker = None
        self._pending_kill_gid: str | None = None

    def compose(self):
        with Vertical():
            with Horizontal(id="fleet-main"):
                yield FleetListPane(id="fleet-list-col")
                yield FleetEventStream(id="fleet-stream-col")
            yield Input(placeholder="/filter…", id="fleet-filter")
            yield Static(
                "[dim]↓/↑ nav  Enter open  / filter  r replay  k kill  q back[/dim]",
                id="fleet-help",
            )
            yield Footer()

    def on_mount(self) -> None:
        pane = self.query_one(FleetListPane)
        try:
            summaries = load_fleet(self._store)
        except Exception:
            summaries = []
        pane.set_rows(summaries)
        pane.focus()  # neutralize default-focus (CRITICAL in challenge.md)

        runs_dir = self._store_root / ".devboard" / "runs"
        if runs_dir.exists():
            from agentboard.tui.tail_worker import RunTailWorker

            # Create a lightweight app-like shim for RunTailWorker callback
            self._tail_worker = RunTailWorker(self, runs_dir)  # type: ignore[arg-type]
            self._tail_timer = self.set_interval(1.0, self._poll_tail)

    def _poll_tail(self) -> None:
        if self._tail_worker is not None:
            self._tail_worker.poll_once()

    def on_stream_event(self, text: str, color: str | None) -> None:
        """RunTailWorker callback — forward to FleetEventStream."""
        try:
            stream = self.query_one(FleetEventStream)
            stream.push_event(text, color)
        except Exception:
            pass

    def on_unmount(self) -> None:
        if self._tail_timer is not None:
            try:
                self._tail_timer.stop()
            except Exception:
                pass
            self._tail_timer = None

    def action_pop_screen_fleet(self) -> None:
        self.app.pop_screen()

    def action_activate_selected(self) -> None:
        pane = self.query_one(FleetListPane)
        visible = pane._visible_rows()
        if pane.selected_index is None or not visible:
            return
        gid = visible[pane.selected_index].gid
        self.post_message(GoalActivated(gid))

    def action_open_filter(self) -> None:
        inp = self.query_one("#fleet-filter", Input)
        inp.add_class("-open")
        inp.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "fleet-filter":
            return
        pane = self.query_one(FleetListPane)
        pane.set_filter(event.value)
        event.input.remove_class("-open")
        event.input.value = ""
        pane.focus()

    def action_replay_selected(self) -> None:
        """redteam C#2: surface feedback instead of silent no-op."""
        pane = self.query_one(FleetListPane)
        visible = pane._visible_rows()
        if pane.selected_index is None or not visible:
            return
        gid = visible[pane.selected_index].gid
        try:
            self.app.commands.dispatch(f"replay {gid}")  # type: ignore[attr-defined]
            self.app.notify(f"replay dispatched for {gid}")
        except Exception as exc:
            self.app.notify(
                f"replay unavailable ({gid}): {exc}", severity="warning"
            )

    def action_kill_selected(self) -> None:
        """redteam H#3: arm confirmation, don't mutate on first keypress."""
        pane = self.query_one(FleetListPane)
        visible = pane._visible_rows()
        if pane.selected_index is None or not visible:
            return
        gid = visible[pane.selected_index].gid
        self._pending_kill_gid = gid
        self.app.notify(
            f"Press y to confirm: mark {gid} blocked", severity="warning"
        )

    def action_confirm_kill(self) -> None:
        """redteam H#3: finalize kill after y confirmation; use GoalStatus enum."""
        from agentboard.models import GoalStatus

        gid = self._pending_kill_gid
        if not gid:
            return
        self._pending_kill_gid = None
        try:
            board = self._store.load_board()
            mutated = False
            for g in board.goals:
                if g.id == gid:
                    g.status = GoalStatus.blocked
                    mutated = True
            if mutated:
                self._store.save_board(board)
                self.app.notify(f"{gid} marked blocked")
            else:
                self.app.notify(f"{gid} not found", severity="warning")
        except Exception as exc:
            self.app.notify(f"kill failed: {exc}", severity="error")

    def action_dismiss_filter(self) -> None:
        """redteam H#4: Escape dismisses filter Input without submitting."""
        try:
            inp = self.query_one("#fleet-filter", Input)
        except Exception:
            return
        inp.value = ""
        inp.remove_class("-open")
        self.query_one(FleetListPane).focus()
