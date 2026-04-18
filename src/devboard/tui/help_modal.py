from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Label


@dataclass(frozen=True)
class HelpEntry:
    key: str
    name: str
    summary: str

    @property
    def haystack(self) -> str:
        return f"{self.key} {self.name} {self.summary}"


DEFAULT_ENTRIES: tuple[HelpEntry, ...] = (
    HelpEntry(":", ":goals", "focus goals list in sidebar"),
    HelpEntry(":", ":runs", "show 5 most-recent runs"),
    HelpEntry(":", ":diff <task>", "load iter diff into diff tab"),
    HelpEntry(":", ":decisions <task>", "load decisions into decisions tab"),
    HelpEntry(":", ":goto <prefix>", "select a goal by id/title prefix"),
    HelpEntry(":", ":learn <query>", "search learnings"),
    HelpEntry("1", "tab diff", "switch context viewer to diff tab"),
    HelpEntry("2", "tab decisions", "switch context viewer to decisions tab"),
    HelpEntry("3", "tab learnings", "switch context viewer to learnings tab"),
    HelpEntry("4", "tab gauntlet", "switch context viewer to gauntlet tab"),
    HelpEntry("5", "tab plan", "switch context viewer to plan tab"),
    HelpEntry("[", "prev tab", "cycle context viewer tabs backward"),
    HelpEntry("]", "next tab", "cycle context viewer tabs forward"),
    HelpEntry("/", "filter", "filter current viewer content"),
    HelpEntry("?", "help", "open this help modal"),
    HelpEntry("esc", "close", "close command line or modal"),
    HelpEntry("ctrl+q", "quit", "exit devboard"),
)


def fuzzy_filter(entries: Iterable[HelpEntry], query: str, threshold: int = 70) -> list[HelpEntry]:
    """Return entries scored >= threshold. Score is max of:
    - fuzz.ratio against name-core (leading ':' stripped, first token)
    - fuzz.partial_ratio against full haystack
    Empty query returns all entries unchanged.
    """
    q = query.strip().lower()
    if not q:
        return list(entries)
    out: list[tuple[float, HelpEntry]] = []
    for e in entries:
        name_core = e.name.lstrip(":").split(" ")[0].lower()
        score = max(
            fuzz.ratio(q, name_core),
            fuzz.partial_ratio(q, e.haystack.lower()),
        )
        if score >= threshold:
            out.append((score, e))
    out.sort(key=lambda t: -t[0])
    return [e for _, e in out]


class HelpModal(ModalScreen):
    """Fuzzy-searchable help dialog triggered by '?'."""

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }
    HelpModal > Vertical {
        background: $panel;
        border: solid $primary;
        padding: 1 2;
        width: 80;
        height: 80%;
    }
    """

    BINDINGS = [Binding("escape", "dismiss", "Close", show=False)]

    def __init__(self, entries: Iterable[HelpEntry] = DEFAULT_ENTRIES) -> None:
        super().__init__()
        self._entries: tuple[HelpEntry, ...] = tuple(entries)

    def compose(self) -> ComposeResult:
        yield Input(placeholder="search commands / keys", id="help-search")
        yield ListView(id="help-list")

    def on_mount(self) -> None:
        self._refresh_list(self._entries)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "help-search":
            return
        self._refresh_list(fuzzy_filter(self._entries, event.value))

    def _refresh_list(self, entries: Iterable[HelpEntry]) -> None:
        lv = self.query_one("#help-list", ListView)
        lv.clear()
        for e in entries:
            lv.append(ListItem(Label(f"{e.key:<8} {e.name:<20} {e.summary}")))
