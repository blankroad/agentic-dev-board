"""DigestWriter — per-run digest.json materializer.

Idempotent by design: iter_count recomputes from `glob(iters/iter-*.json)`
on every update. Never incremented. `per_file_scrubber` folds the
append-only delta records from each iter.json into a path → list map.

Crash-safe: a process that dies between iter.json write and digest
rewrite will simply see the next update recompute from disk state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentboard.storage.file_store import atomic_write

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore


class DigestWriter:
    """Materializes runs/<rid>/digest.json from iter artifacts."""

    def __init__(self, store: "FileStore") -> None:
        self._store = store

    def _run_pile_dir(self, rid: str) -> Path:
        # Private helper in FileStore — reuse via duck-typing.
        return self._store._run_pile_dir(rid)  # type: ignore[attr-defined]

    def _iter_files(self, rid: str) -> list[Path]:
        iters_dir = self._run_pile_dir(rid) / "iters"
        if not iters_dir.exists():
            return []
        return sorted(iters_dir.glob("iter-*.json"))

    def _load_iter(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}

    def _fold_scrubber(self, iter_dicts: list[dict]) -> dict[str, list[str]]:
        """Fold per_file_scrubber_delta maps from each iter into a
        path → [phase_per_iter_in_order] aggregate.

        Delta shape: {"path/to/file.py": "green"} one entry per file
        touched by that iter. Unmapped files in a given iter mean the
        file was not touched in that iter — they do NOT get an entry
        for that iter's position in the sparkline.
        """
        out: dict[str, list[str]] = {}
        for d in iter_dicts:
            delta = d.get("per_file_scrubber_delta", {})
            if not isinstance(delta, dict):
                continue
            for path, phase_marker in delta.items():
                out.setdefault(path, []).append(str(phase_marker))
        return out

    def update(self, rid: str) -> Path:
        """Recompute digest.json for a run. Idempotent.

        `iter_count` reflects *usable* (parseable JSON) iters only so
        consumers (chapter/session writers, MCP get_session) see a count
        that matches the content actually visible downstream.
        `raw_iter_count` exposes the raw glob count for audit/debug
        tools that need to detect corruption.
        """
        pile_dir = self._run_pile_dir(rid)
        digest_path = pile_dir / "digest.json"

        iter_paths = self._iter_files(rid)
        iter_dicts = [self._load_iter(p) for p in iter_paths]
        # A corrupt iter.json round-trips through _load_iter as {} — filter
        # those out of the usable count. Non-empty dicts are usable.
        usable = [d for d in iter_dicts if d]

        verdict_counts: dict[str, int] = {}
        for d in usable:
            v = d.get("verdict")
            if isinstance(v, str) and v:
                verdict_counts[v] = verdict_counts.get(v, 0) + 1

        digest = {
            "schema_version": 1,
            "rid": rid,
            "iter_count": len(usable),
            "raw_iter_count": len(iter_paths),
            "verdict_counts": verdict_counts,
            "per_file_scrubber": self._fold_scrubber(usable),
        }

        pile_dir.mkdir(parents=True, exist_ok=True)
        # sort_keys + fixed indent = byte-identical for idempotent runs
        body = json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True)
        atomic_write(digest_path, body)
        return digest_path
