from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import RichLog, Static
from textual.widget import Widget


class LogView(Widget):
    """Scrollable live log of LLM calls and tool executions."""

    DEFAULT_CSS = """
    LogView {
        height: 1fr;
    }
    LogView RichLog {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold dim]Live Log[/bold dim]", markup=True)
        yield RichLog(id="log_output", highlight=True, markup=True, wrap=True)

    def write(self, text: str) -> None:
        self.query_one("#log_output", RichLog).write(text)

    def write_tool(self, tool_name: str, result: str, error: bool = False) -> None:
        color = "red" if error else "dim green"
        self.write(f"[{color}][tool:{tool_name}][/{color}] {result[:200]}")

    def write_step(self, step: str, detail: str = "") -> None:
        self.write(f"[bold cyan][{step}][/bold cyan] {detail}")

    def write_verdict(self, verdict: str, iteration: int) -> None:
        colors = {"PASS": "green", "RETRY": "yellow", "REPLAN": "red"}
        color = colors.get(verdict, "white")
        self.write(f"[bold {color}]Iter {iteration} → {verdict}[/bold {color}]")

    def clear(self) -> None:
        self.query_one("#log_output", RichLog).clear()
