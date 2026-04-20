"""Real-TTY smoke for `devboard board`.

POSIX-only. Spawns the TUI through pty.openpty() so Textual sees an
actual terminal (not the VirtualConsole that Pilot uses), waits
`timeout_s` seconds, sends Ctrl+Q, escalates to SIGTERM then SIGKILL,
and inspects captured output for a Python traceback marker. Returns a
plain dict so the wrapping MCP tool can JSON-serialize it.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


_ANSI_SGR = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_TRACEBACK_MARKER = "Traceback (most recent call last)"
_CTRL_Q = b"\x11"


def _strip_ansi(text: str | bytes) -> str:
    """Remove ANSI escape sequences for reliable substring search."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if not text:
        return ""
    return _ANSI_SGR.sub("", text)


def _detect_traceback(buffer: str | bytes) -> bool:
    """True if buffer (after ANSI strip) contains a Python traceback marker."""
    return _TRACEBACK_MARKER in _strip_ansi(buffer)


def _build_subprocess_env() -> dict[str, str]:
    """Force Textual-friendly terminal env on the spawned process."""
    env = dict(os.environ)
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = "140"
    env["LINES"] = "42"
    return env


def _open_pty_or_none() -> tuple[int, int] | None:
    """Return (master_fd, slave_fd) or None when pty is unavailable."""
    try:
        import pty as _pty  # noqa: WPS433 — optional stdlib

        return _pty.openpty()
    except Exception:  # noqa: BLE001 — any failure means "unavailable"
        return None


def run_tui_smoke(project_root: Path, timeout_s: float = 3.0) -> dict[str, Any]:
    """Spawn `devboard board` in a real pty, wait, send Ctrl+Q, capture.

    Returns:
        {mounted, crashed, traceback, captured_bytes, duration_s}
        or {skipped_reason: <str>} when the environment can't support it.
    """
    project_root = Path(project_root)

    fds = _open_pty_or_none()
    if fds is None:
        return {"skipped_reason": "pty unavailable"}

    binary = shutil.which("agentboard")
    if binary is None:
        os.close(fds[0])
        os.close(fds[1])
        return {"skipped_reason": "agentboard binary not on PATH"}

    master_fd, slave_fd = fds
    started = time.time()
    captured = bytearray()
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [binary, "board"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=_build_subprocess_env(),
            cwd=str(project_root),
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)
        slave_fd = -1  # marker: already closed

        deadline = started + timeout_s
        while time.time() < deadline and proc.poll() is None:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                captured.extend(chunk)

        # Try graceful quit first
        if proc.poll() is None:
            try:
                os.write(master_fd, _CTRL_Q)
            except OSError:
                pass
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=1.0)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

        # Drain any remaining output after shutdown signal
        try:
            while True:
                ready, _, _ = select.select([master_fd], [], [], 0.05)
                if master_fd not in ready:
                    break
                chunk = os.read(master_fd, 4096)
                if not chunk:
                    break
                captured.extend(chunk)
        except OSError:
            pass

    finally:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if slave_fd != -1:
            try:
                os.close(slave_fd)
            except OSError:
                pass
        try:
            os.close(master_fd)
        except OSError:
            pass

    duration = time.time() - started
    cleaned = _strip_ansi(bytes(captured))
    crashed = _TRACEBACK_MARKER in cleaned
    traceback_text = cleaned if crashed else None
    mounted = len(captured) > 0 and not crashed

    return {
        "mounted": mounted,
        "crashed": crashed,
        "traceback": traceback_text,
        "captured_bytes": len(captured),
        "duration_s": round(duration, 3),
    }
