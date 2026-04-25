"""Uninstaller — reverse of ``install.py``.

Safe by default:

- Removes only ``agentboard-*`` skill directories — foreign skills untouched.
- Strips only the ``agentboard`` MCP server entry — other servers preserved.
- Strips only ``_source: "agentboard"`` tagged hook entries (FM5) — foreign
  hooks preserved. Falls back to a command-suffix match for legacy untagged
  entries written by older project-scope installs (``emit_settings_hooks``
  did not tag).
- Project ``.agentboard/`` and global ``~/.agentboard/`` (user data) are
  preserved unless ``purge_data=True`` is passed.

Returns a structured report so the CLI can print a summary or do a dry run.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

# Hook script filenames written by emit_settings_hooks() into <proj>/.claude/hooks/.
PROJECT_HOOK_SCRIPTS = ("danger-guard.sh", "iron-law-check.sh", "activity-log.py")

# Suffix-match for legacy untagged project hooks (emit_settings_hooks predates _source).
_LEGACY_PROJECT_HOOK_SUFFIXES = tuple(f"/{name}" for name in PROJECT_HOOK_SCRIPTS) + PROJECT_HOOK_SCRIPTS

INSTALL_MARKER = "# agentic-dev-board (auto-installed)"


def _is_agentboard_skill_dir(path: Path) -> bool:
    return path.is_dir() and path.name.startswith("agentboard-")


def uninstall_skills(target: Path) -> list[Path]:
    """Remove every ``agentboard-*`` directory directly under ``target``.

    Foreign skill directories are left intact. Returns the list of removed
    paths (for reporting). If ``target`` does not exist, returns ``[]``.
    """
    removed: list[Path] = []
    if not target.exists():
        return removed
    for child in sorted(target.iterdir()):
        if _is_agentboard_skill_dir(child):
            shutil.rmtree(child)
            removed.append(child)
    return removed


def remove_project_hooks(target_dir: Path) -> list[Path]:
    """Remove the three hook scripts from ``<target_dir>/.claude/hooks/``.

    Leaves the ``hooks/`` directory in place so foreign hooks survive.
    """
    hooks_dir = target_dir / ".claude" / "hooks"
    removed: list[Path] = []
    if not hooks_dir.exists():
        return removed
    for name in PROJECT_HOOK_SCRIPTS:
        f = hooks_dir / name
        if f.exists():
            f.unlink()
            removed.append(f)
    return removed


def _is_agentboard_hook_entry(entry: dict) -> bool:
    """Match by ``_source`` tag (preferred) OR by hook command suffix (legacy)."""
    if entry.get("_source") == "agentboard":
        return True
    for h in entry.get("hooks", []):
        cmd = h.get("command", "")
        if isinstance(cmd, str) and cmd.endswith(_LEGACY_PROJECT_HOOK_SUFFIXES):
            return True
    return False


def strip_settings_hooks(settings_path: Path) -> int:
    """Remove agentboard hook entries from a Claude Code ``settings.json``.

    Works for both project (``<proj>/.claude/settings.json``) and user
    (``~/.claude/settings.json``) scope. Returns the number of entries
    removed. Foreign entries and other settings keys are preserved.
    """
    if not settings_path.exists():
        return 0
    try:
        data = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        return 0
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return 0

    removed = 0
    empty_events: list[str] = []
    for event, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not (isinstance(e, dict) and _is_agentboard_hook_entry(e))]
        removed += len(entries) - len(kept)
        if kept:
            hooks[event] = kept
        else:
            empty_events.append(event)
    for event in empty_events:
        del hooks[event]
    if not hooks:
        del data["hooks"]

    if removed:
        settings_path.write_text(json.dumps(data, indent=2) + "\n")
    return removed


def strip_mcp_entry(target_dir: Path) -> bool:
    """Remove the ``agentboard`` server from ``<target_dir>/.mcp.json``.

    Also removes the legacy ``devboard`` key (renamed package). Returns True
    if anything was removed. Other MCP servers are preserved. Deletes the
    file only if it becomes empty.
    """
    config_path = target_dir / ".mcp.json"
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        return False
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return False

    changed = False
    for key in ("agentboard", "devboard"):
        if key in servers:
            del servers[key]
            changed = True
    if not changed:
        return False
    if not servers:
        del data["mcpServers"]
    if data:
        config_path.write_text(json.dumps(data, indent=2) + "\n")
    else:
        config_path.unlink()
    return True


def strip_opencode_entry(target_dir: Path) -> bool:
    """Remove the ``agentboard`` server from ``<target_dir>/opencode.json``."""
    config_path = target_dir / "opencode.json"
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        return False
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        return False
    if "agentboard" not in mcp:
        return False
    del mcp["agentboard"]
    if not mcp:
        del data["mcp"]
    # Drop $schema if it's the only thing left — it was added solely by us.
    if list(data.keys()) == ["$schema"]:
        config_path.unlink()
        return True
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    return True


def strip_alias_from_rc(rc_path: Path, marker: str = INSTALL_MARKER) -> bool:
    """Remove the marker line + the alias line that follows it.

    Returns True if the file was modified. Idempotent.
    """
    if not rc_path.exists():
        return False
    txt = rc_path.read_text()
    # Match: optional leading newline, marker line, newline, next line (alias),
    # optional trailing newline. Tolerates the alias line being any single
    # non-empty line that follows the marker (covers zsh/bash and fish forms).
    pattern = r"\n?" + re.escape(marker) + r"\n[^\n]*\n?"
    new_txt, n = re.subn(pattern, "", txt, count=1)
    if n == 0:
        return False
    rc_path.write_text(new_txt)
    return True


def detect_rc_path(home: Path | None = None) -> Path | None:
    """Mirror install.sh's shell detection. Returns None if shell is unknown."""
    import os

    home = home or Path.home()
    shell = os.environ.get("SHELL", "/bin/bash")
    name = Path(shell).name
    if name == "zsh":
        return home / ".zshrc"
    if name == "bash":
        return home / ".bashrc"
    if name == "fish":
        return home / ".config" / "fish" / "config.fish"
    return None


def uninstall_global(
    *,
    targets: tuple[str, ...] = ("claude", "opencode"),
    purge_data: bool = False,
    home: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Remove user-scope artifacts.

    - ``~/.claude/skills/agentboard-*``  (claude target)
    - ``~/.config/opencode/skills/agentboard-*``  (opencode target)
    - agentboard-tagged hook entries in ``~/.claude/settings.json``
    - ``~/.agentboard/``  ONLY when ``purge_data=True``
    """
    home = home or Path.home()
    plan: dict = {
        "removed_skills": [],
        "stripped_user_hooks": 0,
        "removed_data": None,
        "scope": "global",
        "targets": list(targets),
        "dry_run": dry_run,
    }

    if "claude" in targets:
        skills_dir = home / ".claude" / "skills"
        plan["removed_skills"].extend(
            str(p) for p in _list_or_remove(skills_dir, dry_run, _is_agentboard_skill_dir)
        )

    if "opencode" in targets:
        skills_dir = home / ".config" / "opencode" / "skills"
        plan["removed_skills"].extend(
            str(p) for p in _list_or_remove(skills_dir, dry_run, _is_agentboard_skill_dir)
        )

    settings = home / ".claude" / "settings.json"
    if dry_run:
        plan["stripped_user_hooks"] = _count_agentboard_hook_entries(settings)
    else:
        plan["stripped_user_hooks"] = strip_settings_hooks(settings)

    if purge_data:
        data_dir = home / ".agentboard"
        if data_dir.exists():
            plan["removed_data"] = str(data_dir)
            if not dry_run:
                shutil.rmtree(data_dir)

    return plan


def uninstall_project(
    *,
    project_root: Path | None = None,
    targets: tuple[str, ...] = ("claude", "opencode"),
    purge_data: bool = False,
    dry_run: bool = False,
) -> dict:
    """Remove project-scope artifacts under ``project_root`` (default: cwd)."""
    proj = (project_root or Path.cwd()).resolve()
    plan: dict = {
        "project_root": str(proj),
        "removed_skills": [],
        "removed_hook_scripts": [],
        "stripped_project_hooks": 0,
        "stripped_mcp": False,
        "stripped_opencode": False,
        "removed_data": None,
        "scope": "project",
        "targets": list(targets),
        "dry_run": dry_run,
    }

    if "claude" in targets:
        skills_dir = proj / ".claude" / "skills"
        plan["removed_skills"].extend(
            str(p) for p in _list_or_remove(skills_dir, dry_run, _is_agentboard_skill_dir)
        )

    if "opencode" in targets:
        skills_dir = proj / ".opencode" / "skills"
        plan["removed_skills"].extend(
            str(p) for p in _list_or_remove(skills_dir, dry_run, _is_agentboard_skill_dir)
        )

    if "claude" in targets:
        if dry_run:
            hooks_dir = proj / ".claude" / "hooks"
            if hooks_dir.exists():
                plan["removed_hook_scripts"] = [
                    str(hooks_dir / name)
                    for name in PROJECT_HOOK_SCRIPTS
                    if (hooks_dir / name).exists()
                ]
            settings = proj / ".claude" / "settings.json"
            plan["stripped_project_hooks"] = _count_agentboard_hook_entries(settings)
        else:
            plan["removed_hook_scripts"] = [str(p) for p in remove_project_hooks(proj)]
            plan["stripped_project_hooks"] = strip_settings_hooks(
                proj / ".claude" / "settings.json"
            )

    if "claude" in targets:
        if dry_run:
            plan["stripped_mcp"] = _has_agentboard_mcp_entry(proj / ".mcp.json")
        else:
            plan["stripped_mcp"] = strip_mcp_entry(proj)
    if "opencode" in targets:
        if dry_run:
            plan["stripped_opencode"] = _has_agentboard_opencode_entry(proj / "opencode.json")
        else:
            plan["stripped_opencode"] = strip_opencode_entry(proj)

    if purge_data:
        data_dir = proj / ".agentboard"
        if data_dir.exists():
            plan["removed_data"] = str(data_dir)
            if not dry_run:
                shutil.rmtree(data_dir)

    return plan


# ── helpers ──────────────────────────────────────────────────────────────────


def _list_or_remove(parent: Path, dry_run: bool, predicate) -> list[Path]:
    """List or remove (depending on dry_run) children of `parent` matching predicate."""
    if not parent.exists():
        return []
    matched = [c for c in sorted(parent.iterdir()) if predicate(c)]
    if not dry_run:
        for p in matched:
            shutil.rmtree(p)
    return matched


def _count_agentboard_hook_entries(settings_path: Path) -> int:
    if not settings_path.exists():
        return 0
    try:
        data = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        return 0
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    count = 0
    for entries in hooks.values():
        if isinstance(entries, list):
            count += sum(
                1 for e in entries if isinstance(e, dict) and _is_agentboard_hook_entry(e)
            )
    return count


def _has_agentboard_mcp_entry(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        return False
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return False
    return "agentboard" in servers or "devboard" in servers


def _has_agentboard_opencode_entry(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        return False
    mcp = data.get("mcp")
    return isinstance(mcp, dict) and "agentboard" in mcp
