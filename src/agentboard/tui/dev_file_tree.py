"""Dev file tree — changed-file list with per-file reviewed checkbox."""

from __future__ import annotations

from textual.widgets import Static

from agentboard.analytics.diff_parser import DiffFile


def render_tree(
    files: list[DiffFile],
    reviewed: set[str],
    per_file_scrubber_data: dict[str, list[str]] | None = None,
) -> str:
    """Render a plain-text file tree.

    Each row: `[✓]/[ ] <path>  +N/-M [<sparkline>]`.

    M1b-extra: when `per_file_scrubber_data` maps a path to a list of
    phase markers, append a colored sparkline (Rich markup) after the
    size column. Rows without data render legacy-style.
    """
    if not files:
        return "no changed files"

    # Lazy import avoids circular dependency at module load
    if per_file_scrubber_data:
        from agentboard.tui.per_file_scrubber import render_sparkline
    else:
        render_sparkline = None  # type: ignore[assignment]

    lines: list[str] = []
    for f in files:
        mark = "[✓]" if f.path in reviewed else "[ ]"
        if f.is_binary:
            size = "binary"
        else:
            size = f"+{f.added}/-{f.removed}"
        row = f"{mark} {f.path}  {size}"
        if render_sparkline is not None:
            phases = per_file_scrubber_data.get(f.path)  # type: ignore[union-attr]
            if phases:
                row += "  " + render_sparkline(phases)
        lines.append(row)
    return "\n".join(lines)


class DevFileTree(Static):
    """Static widget showing the diff file tree + reviewed state."""

    def __init__(
        self,
        files: list[DiffFile] | None = None,
        reviewed: set[str] | None = None,
        per_file_scrubber_data: dict[str, list[str]] | None = None,
        **kwargs,
    ) -> None:
        # M1b-extra: enable Rich markup so render_tree's sparkline
        # markup renders as colored cells instead of literal bracket text.
        kwargs.setdefault("markup", True)
        super().__init__(**kwargs)
        self._files: list[DiffFile] = files or []
        self._reviewed: set[str] = reviewed if reviewed is not None else set()
        self._scrubber_data: dict[str, list[str]] | None = per_file_scrubber_data
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
        per_file_scrubber_data: dict[str, list[str]] | None = None,
    ) -> None:
        if files is not None:
            self._files = files
            # drop reviewed entries that no longer exist
            self._reviewed &= {f.path for f in self._files}
            self._cursor = min(self._cursor, max(len(self._files) - 1, 0))
        if reviewed is not None:
            self._reviewed = reviewed
        if per_file_scrubber_data is not None:
            self._scrubber_data = per_file_scrubber_data
        self.update(render_tree(self._files, self._reviewed, self._scrubber_data))

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
