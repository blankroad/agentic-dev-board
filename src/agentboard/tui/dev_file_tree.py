"""Dev file tree — changed-file list with per-file reviewed checkbox."""

from __future__ import annotations

from textual.widgets import Static

from agentboard.analytics.diff_parser import DiffFile


def render_tree(files: list[DiffFile], reviewed: set[str]) -> str:
    """Render a plain-text file tree.

    Each row: `[✓]/[ ] <path>  +N/-M` (or `binary` marker for binary files).
    """
    if not files:
        return "no changed files"

    lines: list[str] = []
    for f in files:
        mark = "[✓]" if f.path in reviewed else "[ ]"
        if f.is_binary:
            size = "binary"
        else:
            size = f"+{f.added}/-{f.removed}"
        lines.append(f"{mark} {f.path}  {size}")
    return "\n".join(lines)


class DevFileTree(Static):
    """Static widget showing the diff file tree + reviewed state."""

    def __init__(
        self,
        files: list[DiffFile] | None = None,
        reviewed: set[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._files: list[DiffFile] = files or []
        self._reviewed: set[str] = reviewed if reviewed is not None else set()
        self._cursor: int = 0

    @property
    def reviewed(self) -> set[str]:
        return self._reviewed

    def on_mount(self) -> None:
        self.can_focus = True
        self.refresh_render()

    def refresh_render(
        self,
        files: list[DiffFile] | None = None,
        reviewed: set[str] | None = None,
    ) -> None:
        if files is not None:
            self._files = files
            # drop reviewed entries that no longer exist
            self._reviewed &= {f.path for f in self._files}
            self._cursor = min(self._cursor, max(len(self._files) - 1, 0))
        if reviewed is not None:
            self._reviewed = reviewed
        self.update(render_tree(self._files, self._reviewed))

    def toggle_current(self) -> None:
        """Toggle reviewed membership for the file at the current cursor."""
        if not self._files:
            return
        path = self._files[self._cursor].path
        if path in self._reviewed:
            self._reviewed.remove(path)
        else:
            self._reviewed.add(path)
        self.refresh_render()
