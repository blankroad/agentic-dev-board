"""Regression test for parent audit's deferred redteam finding #1.

`src/devboard/tui/plan_markdown.py:_safe_read` called `path.read_text()`
without `encoding="utf-8"`. Under `LC_ALL=C` / `LANG=POSIX` (CI, Alpine,
stripped Docker), `Path.read_text()` falls back to
`locale.getpreferredencoding()` = `US-ASCII` and raises
`UnicodeDecodeError` on any multibyte glyph (em-dash, middot, arrow,
Korean). The except wrapper then returns the `_unreadable_` fallback —
the 5-section narrative silently disappears from the TUI.

Fix: pass `encoding="utf-8"` on every `path.read_text(...)` call site
under `src/devboard/tui/`.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest


def test_safe_read_survives_ascii_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """# guards: read-text-in-compose-must-catch-unicode

    Force the default text encoding resolver to return `"ascii"` when no
    explicit `encoding=` is passed. This simulates the real-world
    `PYTHONUTF8=0 LC_ALL=C` CI environment where `Path.read_text()`
    without an explicit encoding decodes as ASCII and crashes on any
    multibyte UTF-8 byte. Under this harness, only a call site that
    passes `encoding="utf-8"` explicitly survives.

    Then write a UTF-8 file containing an em-dash (U+2014) and call
    PlanMarkdown's `_safe_read`. Expect the returned string to contain
    the em-dash — NOT the fallback (which would indicate the helper
    silently swallowed a UnicodeDecodeError).
    """
    from devboard.tui.plan_markdown import _safe_read

    real_text_encoding = io.text_encoding

    def ascii_when_unspecified(encoding, stacklevel=2):
        # Mirror the real signature: if caller specified encoding, honor it;
        # otherwise return "ascii" to simulate non-UTF-8 locale default.
        if encoding is not None:
            return real_text_encoding(encoding, stacklevel + 1)
        return "ascii"

    monkeypatch.setattr(io, "text_encoding", ascii_when_unspecified)

    target = tmp_path / "plan_summary.md"
    # "text — more" — U+2014 EM DASH encodes as 3 UTF-8 bytes (0xE2 0x80 0x94)
    # which are invalid under strict ASCII decode.
    target.write_text("text — more", encoding="utf-8")

    result = _safe_read(target, fallback="_FALLBACK_SENTINEL_")

    assert result != "_FALLBACK_SENTINEL_", (
        "_safe_read returned fallback under ascii locale — UnicodeDecodeError "
        "was swallowed instead of UTF-8 content being read. Fix: pass "
        "encoding='utf-8' to path.read_text(...)"
    )
    assert "—" in result, (
        f"em-dash (U+2014) missing from _safe_read output: {result!r}"
    )
