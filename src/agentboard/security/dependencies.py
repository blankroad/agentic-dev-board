"""Deterministic dependency-audit classifier for known CVEs."""
from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path


AUDITOR_TIMEOUT_SEC = 60
_PY_LOCKFILES = ("pyproject.toml", "requirements.txt", "Pipfile.lock", "poetry.lock")
_NODE_LOCKFILES = ("package.json",)


def _detect_ecosystem(project_root: Path) -> str | None:
    for name in _PY_LOCKFILES:
        if (project_root / name).exists():
            return "python"
    for name in _NODE_LOCKFILES:
        if (project_root / name).exists():
            return "node"
    return None


def _empty_counts() -> dict[str, int]:
    return {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}


def _parse_pip_audit(stdout: str) -> tuple[dict[str, int], list[dict]]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return _empty_counts(), []
    findings: list[dict] = []
    counts = _empty_counts()
    for dep in data.get("dependencies", []):
        name = dep.get("name", "")
        for vuln in dep.get("vulns", []) or []:
            severity = (vuln.get("fix_versions") and "MEDIUM") or "LOW"
            raw_sev = vuln.get("severity") or vuln.get("aliases", [""])[0]
            if isinstance(raw_sev, str) and raw_sev:
                severity = raw_sev.upper()
            if severity not in counts:
                severity = "LOW"
            counts[severity] += 1
            findings.append({
                "package": name,
                "id": vuln.get("id", ""),
                "severity": severity,
                "fix_versions": vuln.get("fix_versions", []),
            })
    return counts, findings


def _parse_npm_audit(stdout: str) -> tuple[dict[str, int], list[dict]]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return _empty_counts(), []
    counts = _empty_counts()
    findings: list[dict] = []
    meta_sev = (data.get("metadata") or {}).get("vulnerabilities") or {}
    for sev, n in meta_sev.items():
        key = sev.upper()
        if key in counts:
            counts[key] = int(n)
    for name, vuln in (data.get("vulnerabilities") or {}).items():
        findings.append({
            "package": name,
            "severity": str(vuln.get("severity", "")).upper(),
            "via": vuln.get("via"),
        })
    return counts, findings


def check_dependencies(project_root: Path) -> dict:
    project_root = Path(project_root)
    ecosystem = _detect_ecosystem(project_root)
    base = {
        "ecosystem": ecosystem,
        "auditor": None,
        "severity_counts": _empty_counts(),
        "findings": [],
        "skipped_reason": None,
    }
    if ecosystem is None:
        base["skipped_reason"] = "no supported lockfile"
        return base

    if ecosystem == "python":
        binary = shutil.which("pip-audit")
        if not binary:
            base["skipped_reason"] = "pip-audit not found"
            return base
        cmd = [binary, "--format", "json"]
        parser = _parse_pip_audit
        base["auditor"] = "pip-audit"
    else:  # node
        binary = shutil.which("npm")
        if not binary:
            base["skipped_reason"] = "npm not found"
            return base
        cmd = [binary, "audit", "--json"]
        parser = _parse_npm_audit
        base["auditor"] = "npm audit"

    try:
        proc = subprocess.run(
            cmd, cwd=project_root, capture_output=True, text=True,
            timeout=AUDITOR_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        base["skipped_reason"] = "auditor timed out"
        return base
    except FileNotFoundError:
        base["skipped_reason"] = "auditor binary disappeared"
        return base

    stdout = proc.stdout or ""
    if not stdout.strip():
        base["skipped_reason"] = f"auditor exited with code {proc.returncode}"
        return base

    counts, findings = parser(stdout)
    base["severity_counts"] = counts
    base["findings"] = findings
    return base
