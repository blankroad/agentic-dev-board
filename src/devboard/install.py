"""Installer — copy skills to ~/.claude/skills/ (global) or ./.claude/skills/ (project),
install hooks, and emit .mcp.json config. Makes devboard portable across Claude Code
projects and (with format compatibility) OpenCode / Copilot CLI / other skill-aware agents.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def _repo_root() -> Path:
    # src/devboard/install.py → repo root is two levels up
    return Path(__file__).resolve().parent.parent.parent


def _skills_src() -> Path:
    """Find skills/ — try repo layout first, then installed-wheel shared-data."""
    candidates = [
        _repo_root() / "skills",                                    # dev install (pip install -e .)
        Path(__file__).resolve().parent.parent.parent.parent.parent / "share" / "devboard" / "skills",  # wheel
        Path("/usr/local/share/devboard/skills"),                   # system install
        Path.home() / ".local" / "share" / "devboard" / "skills",   # user install
    ]
    for c in candidates:
        if c.exists() and any(c.iterdir()):
            return c
    # Fall back to repo layout even if missing — caller will get clear error
    return _repo_root() / "skills"


def _hooks_src() -> Path:
    candidates = [
        _repo_root() / "hooks",
        Path(__file__).resolve().parent.parent.parent.parent.parent / "share" / "devboard" / "hooks",
        Path("/usr/local/share/devboard/hooks"),
        Path.home() / ".local" / "share" / "devboard" / "hooks",
    ]
    for c in candidates:
        if c.exists() and any(c.iterdir()):
            return c
    return _repo_root() / "hooks"


def install_skills(target: Path, overwrite: bool = False) -> list[Path]:
    """Copy skill directories into target/<skill-name>/SKILL.md."""
    target.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    src = _skills_src()
    if not src.exists():
        raise FileNotFoundError(f"Skills source not found: {src}")

    for skill_dir in sorted(src.iterdir()):
        if not skill_dir.is_dir():
            continue
        dest = target / skill_dir.name
        if dest.exists() and not overwrite:
            continue
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        installed.append(dest)
    return installed


def install_hooks(target: Path, overwrite: bool = False) -> list[Path]:
    """Copy hook shell scripts to target/hooks/."""
    hooks_dest = target / "hooks"
    hooks_dest.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    src = _hooks_src()
    if not src.exists():
        return []

    for hook_file in sorted(src.glob("*.sh")):
        dest = hooks_dest / hook_file.name
        if dest.exists() and not overwrite:
            continue
        shutil.copy2(hook_file, dest)
        dest.chmod(0o755)
        installed.append(dest)
    return installed


def emit_mcp_config(target_dir: Path, python_bin: str | None = None) -> Path:
    """Write .mcp.json so Claude Code loads the devboard MCP server.

    Defaults `python_bin` to `sys.executable` — the Python currently running
    `devboard install`. This means:
      - pip install -e . inside a venv → venv python
      - pipx install → pipx's managed venv python
      - system install → system python
    In all cases the Python has the `mcp` + `devboard` packages available.
    Users can override explicitly via --python flag.
    """
    import sys
    config_path = target_dir / ".mcp.json"
    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            pass

    servers = existing.setdefault("mcpServers", {})
    servers["devboard"] = {
        "command": python_bin or sys.executable,
        "args": ["-m", "devboard.mcp_server"],
    }
    config_path.write_text(json.dumps(existing, indent=2) + "\n")
    return config_path


def emit_settings_hooks(target_dir: Path) -> Path:
    """Merge hook config into .claude/settings.json (project-level)."""
    settings_dir = target_dir / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / "settings.json"

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            pass

    hooks = existing.setdefault("hooks", {})

    pre_use = hooks.setdefault("PreToolUse", [])
    # Avoid duplicate registration
    if not any(
        any(h.get("command", "").endswith("danger-guard.sh") for h in entry.get("hooks", []))
        for entry in pre_use
    ):
        pre_use.append({
            "matcher": "Bash",
            "hooks": [{
                "type": "command",
                "command": ".claude/hooks/danger-guard.sh",
            }],
        })

    post_use = hooks.setdefault("PostToolUse", [])
    if not any(
        any(h.get("command", "").endswith("iron-law-check.sh") for h in entry.get("hooks", []))
        for entry in post_use
    ):
        post_use.append({
            "matcher": "Write|Edit",
            "hooks": [{
                "type": "command",
                "command": ".claude/hooks/iron-law-check.sh",
            }],
        })

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    return settings_path


def install_all(
    scope: str = "project",      # "project" | "global"
    project_root: Path | None = None,
    overwrite: bool = False,
    with_hooks: bool = True,
    with_mcp: bool = True,
    python_bin: str | None = None,
) -> dict:
    """Install skills (+ optional hooks + MCP config).

    scope="global":  skills → ~/.claude/skills/, no project-level hooks/mcp (user manages manually)
    scope="project": skills → <proj>/.claude/skills/, hooks + mcp config in <proj>
    """
    if scope not in ("project", "global"):
        raise ValueError(f"scope must be 'project' or 'global', got {scope!r}")

    result: dict = {"scope": scope, "installed_skills": [], "installed_hooks": [], "mcp_config": None, "settings": None}

    if scope == "global":
        skills_target = Path.home() / ".claude" / "skills"
        result["installed_skills"] = [str(p) for p in install_skills(skills_target, overwrite=overwrite)]
        # Global install does NOT write hooks or .mcp.json — user does this per-project
        # (hooks/MCP are project-scoped in Claude Code)
    else:
        proj = (project_root or Path.cwd()).resolve()
        skills_target = proj / ".claude" / "skills"
        result["installed_skills"] = [str(p) for p in install_skills(skills_target, overwrite=overwrite)]

        if with_hooks:
            hook_target = proj / ".claude"
            result["installed_hooks"] = [str(p) for p in install_hooks(hook_target, overwrite=overwrite)]
            result["settings"] = str(emit_settings_hooks(proj))

        if with_mcp:
            result["mcp_config"] = str(emit_mcp_config(proj, python_bin=python_bin))

    return result
