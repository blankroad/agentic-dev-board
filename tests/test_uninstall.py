"""Uninstall — symmetric reverse of install.py.

Guards on the things uninstall must *not* do (preserve foreign skills, MCP
servers, hooks, settings keys) and the things it *must* do (drop tagged
agentboard entries, remove agentboard-* skills, leave user data alone unless
--purge-data).
"""
from __future__ import annotations

import json
from pathlib import Path

from agentboard import install, uninstall


def _write(path: Path, content: str | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        path.write_text(json.dumps(content, indent=2))
    else:
        path.write_text(content)


# ── uninstall_skills ─────────────────────────────────────────────────────────


def test_uninstall_skills_only_removes_agentboard_prefixed(tmp_path: Path) -> None:
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "agentboard-plan").mkdir()
    (skills / "agentboard-plan" / "SKILL.md").write_text("x")
    (skills / "agentboard-execute").mkdir()
    (skills / "some-other-skill").mkdir()
    (skills / "some-other-skill" / "SKILL.md").write_text("keep")

    removed = uninstall.uninstall_skills(skills)

    names = sorted(p.name for p in removed)
    assert names == ["agentboard-execute", "agentboard-plan"]
    assert (skills / "some-other-skill").exists()
    assert not (skills / "agentboard-plan").exists()


def test_uninstall_skills_handles_missing_target(tmp_path: Path) -> None:
    assert uninstall.uninstall_skills(tmp_path / "does-not-exist") == []


# ── strip_settings_hooks ─────────────────────────────────────────────────────


def test_strip_settings_hooks_drops_tagged_keeps_foreign(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    install.write_user_hooks(
        settings,
        {"PostToolUse": [{"hooks": [{"type": "command", "command": "agent.sh"}]}]},
    )
    # Inject a foreign entry post-install.
    data = json.loads(settings.read_text())
    data["hooks"]["PostToolUse"].append(
        {"hooks": [{"type": "command", "command": "other-plugin.sh"}]}
    )
    data["permissions"] = {"allow": ["Bash(ls)"]}
    settings.write_text(json.dumps(data))

    removed = uninstall.strip_settings_hooks(settings)
    assert removed == 1

    after = json.loads(settings.read_text())
    cmds = [e["hooks"][0]["command"] for e in after["hooks"]["PostToolUse"]]
    assert cmds == ["other-plugin.sh"]
    assert after["permissions"]["allow"] == ["Bash(ls)"]


def test_strip_settings_hooks_legacy_untagged_by_command_suffix(tmp_path: Path) -> None:
    # emit_settings_hooks() (project-scope) writes entries with no _source tag.
    # Uninstall must still recognize them by the well-known command filename.
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": ".claude/hooks/danger-guard.sh"}
                            ],
                        }
                    ],
                    "PostToolUse": [
                        {
                            "matcher": "Write|Edit",
                            "hooks": [
                                {"type": "command", "command": ".claude/hooks/iron-law-check.sh"}
                            ],
                        },
                        {
                            "matcher": ".*",
                            "hooks": [
                                {"type": "command", "command": ".claude/hooks/activity-log.py"}
                            ],
                        },
                    ],
                }
            }
        )
    )
    removed = uninstall.strip_settings_hooks(settings)
    assert removed == 3
    # Empty events dropped, hooks key dropped if empty.
    after = json.loads(settings.read_text())
    assert "hooks" not in after


def test_strip_settings_hooks_idempotent(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"unrelated": True}))
    assert uninstall.strip_settings_hooks(settings) == 0
    assert uninstall.strip_settings_hooks(settings) == 0
    assert json.loads(settings.read_text()) == {"unrelated": True}


def test_strip_settings_hooks_missing_file(tmp_path: Path) -> None:
    assert uninstall.strip_settings_hooks(tmp_path / "nope.json") == 0


# ── strip_mcp_entry ──────────────────────────────────────────────────────────


def test_strip_mcp_entry_preserves_other_servers(tmp_path: Path) -> None:
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "agentboard": {"command": "python", "args": ["-m", "x"]},
                    "other-thing": {"command": "node", "args": ["index.js"]},
                }
            }
        )
    )
    assert uninstall.strip_mcp_entry(tmp_path) is True
    after = json.loads(cfg.read_text())
    assert "agentboard" not in after["mcpServers"]
    assert "other-thing" in after["mcpServers"]


def test_strip_mcp_entry_removes_legacy_devboard_key(tmp_path: Path) -> None:
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"devboard": {"command": "x"}}}))
    assert uninstall.strip_mcp_entry(tmp_path) is True
    # File deleted because mcpServers became empty and was the only key.
    assert not cfg.exists()


def test_strip_mcp_entry_no_op_when_absent(tmp_path: Path) -> None:
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    assert uninstall.strip_mcp_entry(tmp_path) is False
    assert json.loads(cfg.read_text())["mcpServers"]["other"]["command"] == "x"


# ── strip_opencode_entry ─────────────────────────────────────────────────────


def test_strip_opencode_entry_preserves_other_mcp_servers(tmp_path: Path) -> None:
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "mcp": {
                    "agentboard": {"type": "local", "command": ["x"]},
                    "other": {"type": "local", "command": ["y"]},
                },
                "permission": {"mcp": "ask"},
            }
        )
    )
    assert uninstall.strip_opencode_entry(tmp_path) is True
    after = json.loads(cfg.read_text())
    assert "agentboard" not in after["mcp"]
    assert "other" in after["mcp"]
    assert after["permission"]["mcp"] == "ask"


def test_strip_opencode_entry_deletes_file_when_only_schema_left(tmp_path: Path) -> None:
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "mcp": {"agentboard": {"type": "local", "command": ["x"]}},
            }
        )
    )
    assert uninstall.strip_opencode_entry(tmp_path) is True
    assert not cfg.exists()


# ── strip_alias_from_rc ──────────────────────────────────────────────────────


def test_strip_alias_from_rc_removes_marker_and_following_line(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    rc.write_text(
        "export PATH=$PATH:/usr/local/bin\n"
        "\n"
        "# agentic-dev-board (auto-installed)\n"
        'alias agentboard="/Users/me/.local/share/agentic-dev-board/.venv/bin/agentboard"\n'
        "\n"
        "# user's own config below\n"
        "alias ll='ls -la'\n"
    )
    assert uninstall.strip_alias_from_rc(rc) is True
    txt = rc.read_text()
    assert "agentic-dev-board" not in txt
    assert "alias agentboard" not in txt
    assert "alias ll='ls -la'" in txt
    assert "export PATH" in txt


def test_strip_alias_from_rc_no_op_when_marker_absent(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    rc.write_text("alias ll='ls'\n")
    assert uninstall.strip_alias_from_rc(rc) is False
    assert rc.read_text() == "alias ll='ls'\n"


def test_strip_alias_from_rc_idempotent(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    rc.write_text("# agentic-dev-board (auto-installed)\nalias agentboard=\"x\"\n")
    assert uninstall.strip_alias_from_rc(rc) is True
    assert uninstall.strip_alias_from_rc(rc) is False


# ── uninstall_global / uninstall_project (integration) ──────────────────────


def test_uninstall_global_dry_run_makes_no_changes(tmp_path: Path) -> None:
    # Plant some artifacts under fake $HOME.
    home = tmp_path / "home"
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "agentboard-plan").mkdir()
    settings = home / ".claude" / "settings.json"
    install.write_user_hooks(
        settings, {"PostToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]}
    )

    plan = uninstall.uninstall_global(home=home, dry_run=True)
    assert plan["dry_run"] is True
    assert len(plan["removed_skills"]) == 1
    assert plan["stripped_user_hooks"] == 1
    # Nothing actually removed.
    assert (skills / "agentboard-plan").exists()
    assert json.loads(settings.read_text())["hooks"]["PostToolUse"]


def test_uninstall_global_applies_when_not_dry_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "agentboard-plan").mkdir()
    (skills / "foreign-skill").mkdir()
    settings = home / ".claude" / "settings.json"
    install.write_user_hooks(
        settings, {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "x"}]}]}
    )

    plan = uninstall.uninstall_global(home=home)
    assert not (skills / "agentboard-plan").exists()
    assert (skills / "foreign-skill").exists()
    assert plan["stripped_user_hooks"] == 1
    after = json.loads(settings.read_text())
    assert "hooks" not in after  # only entry was agentboard, key is dropped


def test_uninstall_global_purge_data(tmp_path: Path) -> None:
    home = tmp_path / "home"
    data = home / ".agentboard"
    (data / "index").mkdir(parents=True)
    (data / "index" / "learnings.jsonl").write_text("{}\n")

    plan = uninstall.uninstall_global(home=home, purge_data=True)
    assert plan["removed_data"] == str(data)
    assert not data.exists()


def test_uninstall_global_default_preserves_data(tmp_path: Path) -> None:
    home = tmp_path / "home"
    data = home / ".agentboard"
    (data / "index").mkdir(parents=True)

    plan = uninstall.uninstall_global(home=home)
    assert plan["removed_data"] is None
    assert data.exists()


def test_uninstall_project_full_round_trip(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()

    # Simulate a full install footprint.
    install.install_skills(proj / ".claude" / "skills")
    install.install_skills(proj / ".opencode" / "skills")
    install.install_hooks(proj / ".claude")
    install.emit_mcp_config(proj, python_bin="/usr/bin/python3")
    install.emit_opencode_config(proj, python_bin="/usr/bin/python3")
    install.emit_settings_hooks(proj)
    # Plant a foreign MCP server + foreign skill that should survive.
    mcp_data = json.loads((proj / ".mcp.json").read_text())
    mcp_data["mcpServers"]["other-server"] = {"command": "x"}
    (proj / ".mcp.json").write_text(json.dumps(mcp_data))
    (proj / ".claude" / "skills" / "foreign-skill").mkdir()

    plan = uninstall.uninstall_project(project_root=proj)

    assert len(plan["removed_skills"]) >= 2  # claude + opencode agentboard skills
    assert plan["stripped_mcp"] is True
    assert plan["stripped_opencode"] is True
    assert plan["stripped_project_hooks"] >= 1
    assert plan["removed_data"] is None  # default: no purge

    # Foreign survivors.
    assert (proj / ".claude" / "skills" / "foreign-skill").exists()
    after_mcp = json.loads((proj / ".mcp.json").read_text())
    assert "agentboard" not in after_mcp["mcpServers"]
    assert "other-server" in after_mcp["mcpServers"]


def test_uninstall_project_purge_data_removes_agentboard_dir(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / ".agentboard" / "goals").mkdir(parents=True)
    (proj / ".agentboard" / "state.json").write_text("{}")

    plan = uninstall.uninstall_project(project_root=proj, purge_data=True)
    assert plan["removed_data"] == str((proj / ".agentboard").resolve())
    assert not (proj / ".agentboard").exists()
