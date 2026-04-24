"""Rootless resolver + state-dir discovery for Cross-Project Memory.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §"MCP 서버는 project_root=None fallback으로 rootless mode를 지원".
"""

from pathlib import Path

from agentboard import config


def test_resolve_project_root_none_returns_global_fallback(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    assert config.resolve_project_root(None) == fake_home / ".agentboard"


def test_discover_state_dir_falls_back_to_global_when_no_walk_up_hit(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    # cwd has no .agentboard/ walking up → fallback to global.
    assert (
        config.discover_state_dir(tmp_path / "scratchpad")
        == fake_home / ".agentboard"
    )
