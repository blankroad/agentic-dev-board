"""Pile-aware diff loader for Cinema Labor Dev tab (M1b).

Replaces git subprocess as the data source for the Dev tab when a
canonical pile exists for the current run. Provides three lookups:

- load_files_from_pile(rid, store) → list[DiffFile] aggregated across iters
- final_diff_for_file(rid, path, store) → cumulative diff text for one file
- iter_diff_for_file(rid, path, iter_n, store) → single iter slice for file

All three are pure read helpers. No write side effects.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentboard.analytics.diff_parser import DiffFile, parse_unified_diff

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore


def _iter_paths(store: "FileStore", rid: str) -> list[Path]:
    pile_dir = store._run_pile_dir(rid)  # type: ignore[attr-defined]
    iters_dir = pile_dir / "iters"
    if not iters_dir.exists():
        return []
    return sorted(iters_dir.glob("iter-*.json"))


def _load_iter_dict(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _diff_text_for_iter(store: "FileStore", rid: str, iter_dict: dict) -> str:
    """Resolve diff text for an iter using diff_ref or convention.

    Convention fallback: tasks/<tid>/changes/iter_<N>.diff.
    """
    diff_ref = iter_dict.get("diff_ref")
    if not diff_ref:
        return ""
    # Resolve relative to task dir if available
    run_info = store.load_run(rid)
    if run_info is None:
        return ""
    gid = run_info.get("gid")
    tid = run_info.get("tid")
    if not gid or not tid:
        return ""
    task_dir = store._tasks_dir(gid, tid)  # type: ignore[attr-defined]
    diff_path = task_dir / diff_ref
    if not diff_path.exists():
        # Maybe diff_ref is run-relative; try that
        run_dir = store._run_pile_dir(rid)  # type: ignore[attr-defined]
        alt = run_dir / diff_ref
        if alt.exists():
            diff_path = alt
        else:
            return ""
    try:
        return diff_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def load_files_from_pile(rid: str, store: "FileStore") -> list[DiffFile]:
    """Aggregate all files touched across iters into a deduped DiffFile list.

    Latest iter's added/removed counts win when same path appears in
    multiple iters (so caller sees most recent state).
    """
    by_path: dict[str, DiffFile] = {}
    for ipath in _iter_paths(store, rid):
        d = _load_iter_dict(ipath)
        if not d:
            continue
        diff_text = _diff_text_for_iter(store, rid, d)
        if not diff_text:
            continue
        for f in parse_unified_diff(diff_text):
            # Latest iter overwrites — but accumulate added/removed for
            # final-diff-style display. Keep simple: latest wins.
            existing = by_path.get(f.path)
            if existing is None:
                by_path[f.path] = f
            else:
                existing.added += f.added
                existing.removed += f.removed
                existing.hunks.extend(f.hunks)
    return list(by_path.values())


def final_diff_for_file(rid: str, path: str, store: "FileStore") -> str:
    """Concatenate per-iter diff slices for `path` in iter order."""
    parts: list[str] = []
    for ipath in _iter_paths(store, rid):
        d = _load_iter_dict(ipath)
        if not d:
            continue
        diff_text = _diff_text_for_iter(store, rid, d)
        if not diff_text:
            continue
        slice_text = _extract_file_slice(diff_text, path)
        if slice_text:
            parts.append(slice_text)
    return "\n".join(parts)


def iter_diff_for_file(
    rid: str, path: str, iter_n: int, store: "FileStore"
) -> str:
    """Return the single-iter diff slice for `path` at iter `iter_n`."""
    pile_dir = store._run_pile_dir(rid)  # type: ignore[attr-defined]
    target = pile_dir / "iters" / f"iter-{iter_n:03d}.json"
    if not target.exists():
        return ""
    d = _load_iter_dict(target)
    if not d:
        return ""
    diff_text = _diff_text_for_iter(store, rid, d)
    return _extract_file_slice(diff_text, path) if diff_text else ""


def _extract_file_slice(diff_text: str, path: str) -> str:
    """Return only the portion of `diff_text` corresponding to `path`.

    Cuts on `diff --git a/<path> b/<path>` boundaries.
    """
    if not diff_text:
        return ""
    lines = diff_text.splitlines()
    inside = False
    out: list[str] = []
    for ln in lines:
        if ln.startswith("diff --git "):
            # New file boundary
            inside = path in ln  # path appears as "a/<path> b/<path>"
        if inside:
            out.append(ln)
    return "\n".join(out)
