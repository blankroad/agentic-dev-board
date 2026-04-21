"""ThrottleSentinel — TOCTOU-safe critical section for chapter/session
synth decision.

Design:
- Sentinel file `.throttle` lives at runs/<rid>/.throttle
- JSON shape: {"last_synth_iter": int, "last_phase": str | null}
- Decision rule (monotonic, no wall-clock):
    should_synth = (no sentinel) OR (current_iter - last_synth_iter >= N)
                   OR (current_phase != last_phase)
  where N = 5 by default.
- Critical section uses fcntl.flock(LOCK_EX) on `.throttle` itself
  (not a sibling lock file). Open with "a+" so the file is created
  atomically on first access, then flock on the returned fd serializes
  read→decide→(optional)write→release in one step.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore


SYNTH_ITER_DELTA = 5


class ThrottleSentinel:
    """Per-rid synth gate with fcntl-flock critical section."""

    def __init__(self, store: "FileStore", iter_delta: int = SYNTH_ITER_DELTA) -> None:
        self._store = store
        self._iter_delta = iter_delta

    def _sentinel_path(self, rid: str) -> Path:
        return self._store._run_pile_dir(rid) / ".throttle"  # type: ignore[attr-defined]

    def decide_and_commit(self, rid: str, iter_n: int, phase: str) -> bool:
        """Atomically decide whether synth is due, committing state on True.

        Semantics: caller treats True as "please run synth now; sentinel
        has been updated to reflect this iter as last_synth." False means
        "skip synth for now; no state change."

        On True, the write happens BEFORE returning so subsequent callers
        see the updated sentinel without waiting for synth to finish. The
        synth itself is idempotent (digest / chapter writers recompute
        from iter files), so a failed synth will be retried on the next
        eligible iter.
        """
        path = self._sentinel_path(rid)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Open with "a+" to create-or-open atomically. "r+" would require
        # the file to exist already, triggering its own TOCTOU (check-
        # exists then open). Using "a+" means the file exists by the
        # time fcntl.flock is called — single atomic system call to
        # establish the exclusive lock.
        with open(path, "a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read()
                state = self._parse_state(raw)
                last_synth = state.get("last_synth_iter")
                last_phase = state.get("last_phase")

                if last_synth is None:
                    should = True
                elif phase != last_phase:
                    should = True
                elif iter_n - last_synth >= self._iter_delta:
                    should = True
                else:
                    should = False

                if should:
                    new_state = {"last_synth_iter": iter_n, "last_phase": phase}
                    self._write_state(path, new_state)
                return should
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _parse_state(raw: str) -> dict:
        raw = raw.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Corrupted sentinel — treat as fresh
            return {}
        if not isinstance(parsed, dict):
            return {}
        return parsed

    @staticmethod
    def _write_state(path: Path, state: dict) -> None:
        """Atomic rewrite of the sentinel file.

        Uses temp-file + rename so a process that dies mid-write cannot
        leave a partial / zero-byte sentinel that other processes would
        misinterpret.
        """
        fd, tmp = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(json.dumps(state, ensure_ascii=False))
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
