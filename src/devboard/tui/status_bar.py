from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class StatusBar(Widget):
    """Single-line top bar absorbing v2.0's LiveStream into a compact
    summary: '● goal ▶ iter N phase ◆ redteam verdict ≡ tests'."""

    DEFAULT_CSS = """
    StatusBar { height: 1; background: $primary-darken-3; padding: 0 1; }
    StatusBar #status-bar-body { color: $text; }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._goal_title = ""
        self._iter_n: int | None = None
        self._phase = ""
        self._redteam = ""
        self._tests: int | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._format(), id="status-bar-body", markup=False)

    def set_segments(
        self,
        goal_title: str = "",
        iter_n: int | None = None,
        phase: str = "",
        redteam: str = "",
        tests: int | None = None,
    ) -> None:
        self._goal_title = goal_title
        self._iter_n = iter_n
        self._phase = phase
        self._redteam = redteam
        self._tests = tests
        try:
            self.query_one("#status-bar-body", Static).update(self._format())
        except Exception:
            pass

    def _format(self) -> str:
        segments: list[str] = []
        if self._goal_title:
            segments.append(f"● {self._goal_title}")
        if self._iter_n is not None:
            phase = f" {self._phase}" if self._phase else ""
            segments.append(f"▶ iter {self._iter_n}{phase}")
        if self._redteam:
            segments.append(f"◆ redteam {self._redteam}")
        if self._tests is not None:
            segments.append(f"≡ {self._tests} tests")
        return "  ".join(segments) if segments else "devboard"
