"""Tier classification rules for Cross-Project Memory path filter.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 — Tier 1 (installed project)
vs Tier 2 (ambient non-init project) vs skip (home / system paths).
"""

from pathlib import Path

from agentboard.storage import path_filter


def test_resolve_tier_home_returns_skip() -> None:
    assert path_filter.resolve_tier(Path.home()) == "skip"


def test_resolve_tier_tmp_returns_tier2() -> None:
    assert path_filter.resolve_tier(Path("/tmp/xyz")) == "tier2"


def test_resolve_tier_walks_up_to_agentboard_returns_tier1(tmp_path: Path) -> None:
    (tmp_path / ".agentboard").mkdir()
    deep = tmp_path / "src" / "pkg"
    deep.mkdir(parents=True)
    assert path_filter.resolve_tier(deep) == "tier1"


def test_resolve_tier_git_only_is_tier2_agentboard_flips_to_tier1(tmp_path: Path) -> None:
    # FM4 3-state boundary: .git/ alone is NOT a tier1 marker — only .agentboard/ is.
    (tmp_path / ".git").mkdir()
    assert path_filter.resolve_tier(tmp_path) == "tier2"
    (tmp_path / ".agentboard").mkdir()
    assert path_filter.resolve_tier(tmp_path) == "tier1"


def test_resolve_tier_honors_ignore_paths_exact_prefix(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    # FM7 escape hatch: ~/.agentboard/ignore_paths.txt exact-prefix match → skip.
    fake_home = tmp_path / "home"
    (fake_home / ".agentboard").mkdir(parents=True)
    (fake_home / ".agentboard" / "ignore_paths.txt").write_text("/opt/secret\n")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    assert path_filter.resolve_tier(Path("/opt/secret/project")) == "skip"
