"""Verify the autouse home_tmpdir session fixture is wired (FM2 guard).

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 challenge.md FM2 — Tier 1
write-through must not silently mutate the developer's real ~/.agentboard/.
"""

from pathlib import Path


def test_home_tmpdir_fixture_is_session_tmpdir(home_tmpdir: Path) -> None:
    assert home_tmpdir.is_dir()
    assert "agentboard_home" in home_tmpdir.name
