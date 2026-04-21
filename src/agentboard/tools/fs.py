from __future__ import annotations

from pathlib import Path

from agentboard.tools.base import ToolDef, ToolRegistry


def _resolve(root: Path, path: str) -> Path:
    p = (root / path).resolve()
    if not str(p).startswith(str(root.resolve())):
        raise PermissionError(f"Path '{path}' is outside project root")
    return p


def _check_scope(
    resolved: Path,
    root: Path,
    touches: list[str],
    forbids: list[str],
    operation: str,
) -> str | None:
    """Return an error string if scope is violated, else None."""
    rel = str(resolved.relative_to(root.resolve()))

    # forbids are hard-blocked for all operations
    for guard in forbids:
        if rel.startswith(guard.lstrip("/")) or guard.lstrip("/") in rel:
            return f"ERROR: Path '{rel}' is in out_of_scope_guard ('{guard}') — halting"

    # touches restrict writes (reads are always allowed within root)
    if operation == "write" and touches:
        allowed = any(
            rel.startswith(t.lstrip("/")) or t.lstrip("/") in rel
            for t in touches
        )
        if not allowed:
            return f"ERROR: Path '{rel}' not in task's declared touches list"

    return None


def make_fs_tools(
    root: Path,
    registry: ToolRegistry,
    touches: list[str] | None = None,
    forbids: list[str] | None = None,
) -> None:
    _touches = touches or []
    _forbids = forbids or []

    def fs_read(path: str) -> str:
        try:
            p = _resolve(root, path)
        except PermissionError as e:
            return f"ERROR: {e}"
        err = _check_scope(p, root, _touches, _forbids, "read")
        if err:
            return err
        if not p.exists():
            return f"ERROR: File not found: {path}"
        return p.read_text()

    def fs_write(path: str, content: str) -> str:
        try:
            p = _resolve(root, path)
        except PermissionError as e:
            return f"ERROR: {e}"
        err = _check_scope(p, root, _touches, _forbids, "write")
        if err:
            return err
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Written {len(content)} bytes to {path}"

    def fs_list(path: str = ".") -> str:
        try:
            p = _resolve(root, path)
        except PermissionError as e:
            return f"ERROR: {e}"
        err = _check_scope(p, root, _touches, _forbids, "read")
        if err:
            return err
        if not p.exists():
            return f"ERROR: Directory not found: {path}"
        if not p.is_dir():
            return f"ERROR: Not a directory: {path}"
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = []
        for e in entries:
            suffix = "/" if e.is_dir() else ""
            lines.append(f"{e.name}{suffix}")
        return "\n".join(lines) if lines else "(empty)"

    registry.register(
        ToolDef(
            name="fs_read",
            description="Read a file's contents. Path is relative to project root.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative file path"}},
                "required": ["path"],
            },
        ),
        fs_read,
    )
    registry.register(
        ToolDef(
            name="fs_write",
            description="Write content to a file, creating parent directories as needed.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        ),
        fs_write,
    )
    registry.register(
        ToolDef(
            name="fs_list",
            description="List directory contents. Path is relative to project root.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative directory path (default '.')"}},
                "required": [],
            },
        ),
        fs_list,
    )
