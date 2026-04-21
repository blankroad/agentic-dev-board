from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


# ── Ecosystem detection + skipped reasons ────────────────────────────────────

def test_no_lockfile_returns_skipped(tmp_path: Path):
    from agentboard.security.dependencies import check_dependencies
    result = check_dependencies(tmp_path)
    assert result["skipped_reason"] == "no supported lockfile"
    assert result["ecosystem"] is None


def test_python_ecosystem_detected(tmp_path: Path, monkeypatch):
    from agentboard.security import dependencies
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.setattr(dependencies.shutil, "which", lambda name: None)
    result = dependencies.check_dependencies(tmp_path)
    assert result["ecosystem"] == "python"


def test_node_ecosystem_detected(tmp_path: Path, monkeypatch):
    from agentboard.security import dependencies
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setattr(dependencies.shutil, "which", lambda name: None)
    result = dependencies.check_dependencies(tmp_path)
    assert result["ecosystem"] == "node"


def test_missing_pip_audit_returns_skipped(tmp_path: Path, monkeypatch):
    from agentboard.security import dependencies
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.setattr(dependencies.shutil, "which", lambda name: None)
    result = dependencies.check_dependencies(tmp_path)
    assert "pip-audit" in result["skipped_reason"]


# ── Parser correctness ──────────────────────────────────────────────────────

_PIP_AUDIT_PAYLOAD = json.dumps({
    "dependencies": [
        {
            "name": "requests",
            "version": "2.20.0",
            "vulns": [
                {"id": "GHSA-x", "severity": "high", "fix_versions": ["2.31.0"]},
                {"id": "GHSA-y", "severity": "critical", "fix_versions": []},
            ],
        },
        {"name": "urllib3", "version": "1.24", "vulns": []},
    ]
})

_NPM_AUDIT_PAYLOAD = json.dumps({
    "metadata": {"vulnerabilities": {"critical": 1, "high": 2, "moderate": 0, "low": 3}},
    "vulnerabilities": {
        "lodash": {"severity": "high", "via": ["CVE-x"]},
        "minimist": {"severity": "critical", "via": ["CVE-y"]},
    },
})


class _FakeCompleted:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def test_pip_audit_parse(tmp_path: Path, monkeypatch):
    from agentboard.security import dependencies
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.setattr(dependencies.shutil, "which", lambda name: "/usr/bin/pip-audit")
    monkeypatch.setattr(dependencies.subprocess, "run",
                        lambda *a, **kw: _FakeCompleted(_PIP_AUDIT_PAYLOAD))
    result = dependencies.check_dependencies(tmp_path)
    assert result["ecosystem"] == "python"
    assert result["auditor"] == "pip-audit"
    assert result["severity_counts"]["HIGH"] == 1
    assert result["severity_counts"]["CRITICAL"] == 1
    assert len(result["findings"]) == 2


def test_npm_audit_parse(tmp_path: Path, monkeypatch):
    from agentboard.security import dependencies
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setattr(dependencies.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(dependencies.subprocess, "run",
                        lambda *a, **kw: _FakeCompleted(_NPM_AUDIT_PAYLOAD, returncode=1))
    result = dependencies.check_dependencies(tmp_path)
    assert result["ecosystem"] == "node"
    assert result["auditor"] == "npm audit"
    assert result["severity_counts"]["CRITICAL"] == 1
    assert result["severity_counts"]["HIGH"] == 2
    assert result["severity_counts"]["LOW"] == 3
    assert {f["package"] for f in result["findings"]} == {"lodash", "minimist"}


# ── MCP registration + dispatch ─────────────────────────────────────────────

def test_mcp_tool_registered():
    from agentboard.mcp_server import list_tools
    tools = asyncio.run(list_tools())
    assert "agentboard_check_dependencies" in {t.name for t in tools}


def test_mcp_dispatch(tmp_path: Path, monkeypatch):
    from agentboard.mcp_server import call_tool
    from agentboard.security import dependencies
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.setattr(dependencies.shutil, "which", lambda name: None)
    result = asyncio.run(call_tool(
        "agentboard_check_dependencies",
        {"project_root": str(tmp_path)},
    ))
    payload = json.loads(result[0].text)
    assert payload["ecosystem"] == "python"
    assert "pip-audit" in payload["skipped_reason"]
