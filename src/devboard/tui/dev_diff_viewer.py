"""Dev diff viewer — renders a unified diff with a 500-line cap.

Pure render helper + Static wrapper. Empty input → empty-state string.
"""

from __future__ import annotations

from textual.widgets import Static

MAX_LINES: int = 500


def render_diff(text: str) -> str:
    """Render a unified-diff string, capping at MAX_LINES lines."""
    if not text or not text.strip():
        return "no diff available — start TDD to populate"

    lines = text.splitlines()
    if len(lines) <= MAX_LINES:
        return "\n".join(lines)
    shown = lines[:MAX_LINES]
    remaining = len(lines) - MAX_LINES
    shown.append(f"… [{remaining} more lines — open externally]")
    return "\n".join(shown)


class DevDiffViewer(Static):
    def __init__(self, diff_text: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._diff_text = diff_text

    def on_mount(self) -> None:
        self.refresh_render()

    def refresh_render(self, diff_text: str | None = None) -> None:
        if diff_text is not None:
            self._diff_text = diff_text
        self.update(render_diff(self._diff_text))
