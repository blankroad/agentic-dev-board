from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PushResult:
    success: bool
    branch: str = ""
    pr_url: str = ""
    error: str = ""


def ensure_branch(project_root: Path, branch: str) -> bool:
    """Create branch if it doesn't exist, or check it out."""
    cwd = str(project_root)
    try:
        # Check if branch already exists
        result = subprocess.run(
            ["git", "branch", "--list", branch],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        if branch in result.stdout:
            subprocess.run(["git", "checkout", branch], check=True, cwd=cwd, capture_output=True, timeout=10)
        else:
            subprocess.run(["git", "checkout", "-b", branch], check=True, cwd=cwd, capture_output=True, timeout=10)
        return True
    except subprocess.CalledProcessError as e:
        return False


def git_push(project_root: Path, branch: str, remote: str = "origin") -> bool:
    try:
        subprocess.run(
            ["git", "push", "-u", remote, branch],
            check=True, cwd=str(project_root), capture_output=True, timeout=60,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def gh_pr_create(
    project_root: Path,
    title: str,
    body: str,
    base_branch: str = "main",
    draft: bool = False,
) -> str:
    """Create a GitHub PR via gh CLI. Returns PR URL or empty string on failure."""
    try:
        cmd = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base_branch]
        if draft:
            cmd.append("--draft")
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, cwd=str(project_root), timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except Exception:
        return ""


def push_and_create_pr(
    project_root: Path,
    branch: str,
    pr_title: str,
    pr_body: str,
    base_branch: str = "main",
    remote: str = "origin",
    draft: bool = False,
) -> PushResult:
    """Ensure branch, push, and create PR. Returns PushResult."""
    if not git_push(project_root, branch, remote):
        return PushResult(success=False, branch=branch, error=f"git push failed for branch '{branch}'")

    pr_url = gh_pr_create(project_root, pr_title, pr_body, base_branch, draft)
    if not pr_url:
        return PushResult(
            success=False, branch=branch,
            error="gh pr create failed — check gh auth and remote settings",
        )

    return PushResult(success=True, branch=branch, pr_url=pr_url)
