"""Parse unified git diff text into structured DiffFile records.

Pure function. No subprocess, no file I/O — callers feed already-loaded
diff text. Handles binary markers and empty input gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiffHunk:
    header: str  # "@@ -1,3 +1,4 @@"
    lines: list[str] = field(default_factory=list)


@dataclass
class DiffFile:
    path: str
    added: int = 0
    removed: int = 0
    hunks: list[DiffHunk] = field(default_factory=list)
    is_binary: bool = False


def parse_unified_diff(text: str) -> list[DiffFile]:
    """Parse `git diff --unified` text into a list of DiffFile records.

    - Empty / whitespace-only input → `[]`.
    - `Binary files X and Y differ` → DiffFile(is_binary=True).
    - Multiple files (each starts with `diff --git a/... b/...`) → multiple
      DiffFile records in input order.
    """
    if not text or not text.strip():
        return []

    files: list[DiffFile] = []
    current: DiffFile | None = None
    current_hunk: DiffHunk | None = None

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            # start new file
            if current is not None:
                if current_hunk is not None:
                    current.hunks.append(current_hunk)
                    current_hunk = None
                files.append(current)
            # parse path: "diff --git a/<path> b/<path>"
            parts = raw.split()
            path = ""
            if len(parts) >= 4 and parts[2].startswith("a/"):
                path = parts[2][2:]
            current = DiffFile(path=path)
            continue

        if current is None:
            continue

        if raw.startswith("Binary files "):
            current.is_binary = True
            continue

        if raw.startswith("+++ ") or raw.startswith("--- ") or raw.startswith("index "):
            continue

        if raw.startswith("@@"):
            if current_hunk is not None:
                current.hunks.append(current_hunk)
            current_hunk = DiffHunk(header=raw)
            continue

        if current_hunk is not None:
            current_hunk.lines.append(raw)
        # count +/- excluding headers (+++ / ---)
        if raw.startswith("+") and not raw.startswith("+++"):
            current.added += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            current.removed += 1

    # flush tail
    if current is not None:
        if current_hunk is not None:
            current.hunks.append(current_hunk)
        files.append(current)

    return files
