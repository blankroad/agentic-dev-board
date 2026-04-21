"""Structural tests for M1a-plumbing docs (p_011)."""
from __future__ import annotations

from pathlib import Path


def test_plumbing_docs_exist_and_have_required_sections() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    phases = repo_root / "docs" / "phases.md"
    mcp_tools = repo_root / "docs" / "mcp_tools.md"
    security = repo_root / "docs" / "security.md"
    readme = repo_root / "README.md"

    assert phases.exists(), f"docs/phases.md missing"
    assert mcp_tools.exists(), f"docs/mcp_tools.md missing"
    assert security.exists(), f"docs/security.md missing"
    assert readme.exists(), f"README.md missing"

    phases_content = phases.read_text(encoding="utf-8")
    assert "PhaseRenderer" in phases_content
    assert "to_dict" in phases_content  # canonical projection
    assert "TddRenderer" in phases_content  # worked example

    mcp_content = mcp_tools.read_text(encoding="utf-8")
    assert "agentboard_get_session" in mcp_content
    assert "agentboard_get_chapter" in mcp_content
    assert "PILE_ABSENT" in mcp_content

    security_content = security.read_text(encoding="utf-8")
    assert "prompt injection" in security_content.lower() or "prompt-injection" in security_content.lower()
    assert "pile" in security_content.lower()

    readme_content = readme.read_text(encoding="utf-8")
    assert "For agent authors" in readme_content or "Agent authors" in readme_content
