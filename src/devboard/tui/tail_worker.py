from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devboard.tui.anomaly import AnomalyClassifier
    from devboard.tui.app import DevBoardApp


class FileTail:
    """Stateful JSONL tail reader. Tracks byte offset across polls and
    buffers a trailing partial line (possibly containing an incomplete
    multi-byte UTF-8 char) until a newline arrives.

    Intended to be driven at ~100ms intervals from a Textual ``@work``
    thread. Pure I/O — no threading concerns here; the caller owns
    scheduling and cross-thread UI updates.

    Opens in binary mode and decodes complete lines as UTF-8 so that a
    poll landing mid-multibyte-char (red-team A3) does not raise
    UnicodeDecodeError.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._offset = 0
        self._buffer = b""

    def read_new_lines(self) -> list[str]:
        if not self._path.exists():
            return []

        try:
            size = self._path.stat().st_size
        except FileNotFoundError:
            return []

        if size < self._offset:
            # File truncated / rotated — reset
            self._offset = 0
            self._buffer = b""

        if size == self._offset:
            return []

        with self._path.open("rb") as fh:
            fh.seek(self._offset)
            chunk = fh.read(size - self._offset)
        self._offset = size

        data = self._buffer + chunk
        if b"\n" not in data:
            self._buffer = data
            return []

        parts = data.split(b"\n")
        # Last element is the tail after the final '\n' — empty if data ends
        # with '\n', otherwise a partial line (possibly with a half
        # multi-byte char) to buffer for next poll.
        self._buffer = parts[-1]
        out: list[str] = []
        for p in parts[:-1]:
            if not p:
                continue
            try:
                out.append(p.decode("utf-8"))
            except UnicodeDecodeError:
                # Malformed completed line — drop and keep tailing.
                continue
        return out


class RunTailWorker:
    """Driver that ties FileTail(s) to AnomalyClassifier and the App's
    stream/health surfaces. One poll advances every tracked run file once
    and forwards new lines to the App via ``on_stream_event``.

    Runs on the Textual event loop via ``App.set_interval`` — not a real
    thread — which keeps UI updates synchronous and avoids cross-thread
    concerns. Still bounded per-poll by FileTail's chunked read.
    """

    def __init__(self, app: "DevBoardApp", runs_dir: Path) -> None:
        from devboard.tui.anomaly import AnomalyClassifier

        self._app = app
        self._runs_dir = runs_dir
        self._tails: dict[Path, FileTail] = {}
        self._classifier: AnomalyClassifier = AnomalyClassifier()

    def poll_once(self) -> None:
        try:
            self._poll_once_inner()
        except Exception:  # noqa: BLE001 — worker must never die silently
            # Future: log via notify; swallow to keep the interval alive.
            return

    def _poll_once_inner(self) -> None:
        if not self._runs_dir.exists():
            return
        for path in sorted(self._runs_dir.glob("*.jsonl")):
            tail = self._tails.setdefault(path, FileTail(path))
            for raw in tail.read_new_lines():
                try:
                    record: object = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                anomaly = self._classifier.classify(record)
                color = anomaly[0] if anomaly is not None else None
                self._app.on_stream_event(raw, color)
