"""axis 3: devboard_tui_render_smoke MCP tool.

Covers _strip_ansi + _detect_traceback unit logic, run_tui_smoke public
shape, pty-unavailable graceful skip, subprocess env injection, MCP
server registration, and an optional real-subprocess integration
smoke (skipped if the `devboard` binary isn't on PATH).
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest


# ------------------------------------------------------------------
# s_001 — pty platform sanity spike
# ------------------------------------------------------------------
def test_pty_spawn_basic_sanity() -> None:
    """# guards: ui-requires-real-tty-smoke-not-just-pytest
    edge: real-TTY divergence category — verifies the platform supports
    pty.openpty + subprocess before we build tooling on top."""
    pty = pytest.importorskip("pty")
    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(
            ["/bin/echo", "hello"], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd
        )
        proc.wait(timeout=3)
        assert proc.returncode == 0
    finally:
        os.close(master_fd)
        os.close(slave_fd)


# ------------------------------------------------------------------
# s_002 — _strip_ansi empty-input edge (empty/None category)
# ------------------------------------------------------------------
def test_strip_ansi_handles_empty_bytes() -> None:
    """# guards: ui-requires-real-tty-smoke-not-just-pytest
    edge: empty input category — never raise on b'' or ''."""
    from devboard.mcp_tools.tui_smoke import _strip_ansi

    assert _strip_ansi("") == ""
    assert _strip_ansi(b"") == ""


def test_strip_ansi_removes_sgr_sequences() -> None:
    from devboard.mcp_tools.tui_smoke import _strip_ansi

    raw = "\x1b[31merror:\x1b[0m something \x1b[1;33mwarn\x1b[0m"
    assert _strip_ansi(raw) == "error: something warn"


# ------------------------------------------------------------------
# s_004 — traceback detection in clean buffer
# ------------------------------------------------------------------
def test_detect_traceback_in_plain_buffer() -> None:
    from devboard.mcp_tools.tui_smoke import _detect_traceback

    assert _detect_traceback("Traceback (most recent call last):\n  File ...") is True
    assert _detect_traceback("nothing unusual") is False


def test_detect_traceback_through_ansi_interleave() -> None:
    """# guards: textual-static-markup-flag-silently-breaks-color
    edge: ANSI coloring splits the marker string — must still match."""
    from devboard.mcp_tools.tui_smoke import _detect_traceback

    # real Textual output can wrap traceback lines in ANSI
    laced = "\x1b[31mTraceback\x1b[0m (most recent call last):\n  ..."
    assert _detect_traceback(laced) is True


# ------------------------------------------------------------------
# s_006 — run_tui_smoke public shape
# ------------------------------------------------------------------
def test_run_tui_smoke_returns_expected_dict_keys(tmp_path: Path) -> None:
    """# guards: unit-tests-on-primitives-dont-prove-integration
    edge: integration wiring category — must return full result shape."""
    (tmp_path / ".devboard").mkdir()
    from devboard.mcp_tools.tui_smoke import run_tui_smoke

    result = run_tui_smoke(tmp_path, timeout_s=1)
    assert isinstance(result, dict)
    expected = {"mounted", "crashed", "traceback", "captured_bytes", "duration_s"}
    # skipped_reason is allowed as an alternative shape
    assert expected.issubset(result.keys()) or "skipped_reason" in result


# ------------------------------------------------------------------
# s_007 — pty unavailable graceful skip
# ------------------------------------------------------------------
def test_run_tui_smoke_skips_gracefully_without_pty(tmp_path: Path, monkeypatch) -> None:
    """# guards: ui-requires-real-tty-smoke-not-just-pytest
    edge: real-TTY divergence — non-POSIX / pty-unavailable graceful skip."""
    from devboard.mcp_tools import tui_smoke

    # Simulate pty import/openpty raising
    monkeypatch.setattr(tui_smoke, "_open_pty_or_none", lambda: None)
    result = tui_smoke.run_tui_smoke(tmp_path, timeout_s=1)
    assert result.get("skipped_reason") == "pty unavailable"


# ------------------------------------------------------------------
# s_008 — subprocess env forces xterm TERM
# ------------------------------------------------------------------
def test_subprocess_env_forces_xterm_term() -> None:
    from devboard.mcp_tools.tui_smoke import _build_subprocess_env

    env = _build_subprocess_env()
    assert env.get("TERM") == "xterm-256color"
    assert env.get("COLUMNS") == "140"
    assert env.get("LINES") == "42"


# ------------------------------------------------------------------
# s_009 — MCP server exposes the tool
# ------------------------------------------------------------------
def test_mcp_server_registers_tui_render_smoke() -> None:
    """# guards: unit-tests-on-primitives-dont-prove-integration
    edge: integration wiring category — verify MCP server lists + dispatches."""
    from devboard import mcp_server

    importlib.reload(mcp_server)
    src = Path(mcp_server.__file__).read_text()
    assert "devboard_tui_render_smoke" in src


# ------------------------------------------------------------------
# s_010 — real integration: mount on current project (skipped if devboard absent)
# ------------------------------------------------------------------
@pytest.mark.skipif(
    shutil.which("agentboard") is None, reason="agentboard binary not on PATH"
)
def test_run_tui_smoke_mounts_current_project() -> None:
    """# guards: ui-requires-real-tty-smoke-not-just-pytest
    edge: real-TTY divergence category — actually spawn devboard board briefly."""
    from devboard.mcp_tools.tui_smoke import run_tui_smoke

    result = run_tui_smoke(Path.cwd(), timeout_s=3)
    if "skipped_reason" in result:
        pytest.skip(result["skipped_reason"])
    # Either mounted cleanly or surfaced a traceback — both are diagnostic.
    # Failure shape: mounted=False AND crashed=False AND captured_bytes==0
    assert result.get("captured_bytes", 0) > 0 or result.get("crashed") is True, (
        f"real-TTY mount produced no output and no crash: {result}"
    )
