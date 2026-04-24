"""FM5 guard — writing user hooks into ~/.claude/settings.json must preserve
existing hooks + permissions from prior installers / other plugins.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 challenge.md Failure Mode 5.
"""

import json
from pathlib import Path

from agentboard import install


def test_write_user_hooks_preserves_existing_entries(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    existing = {
        "permissions": {"allow": ["Bash(python *)"]},
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [{"type": "command", "command": "existing.sh"}],
                }
            ]
        },
    }
    settings.write_text(json.dumps(existing))
    install.write_user_hooks(
        settings,
        {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "new.sh"}]}]},
    )
    merged = json.loads(settings.read_text())
    assert merged["permissions"]["allow"] == ["Bash(python *)"]
    assert merged["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "existing.sh"
    assert (
        merged["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "new.sh"
    )


def test_write_user_hooks_is_idempotent_on_reinstall(tmp_path: Path) -> None:
    # FM5: reinstalling must not duplicate agentboard-owned entries.
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({}))
    entries = {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "agentboard-hook.sh"}]}
        ]
    }
    install.write_user_hooks(settings, entries)
    install.write_user_hooks(settings, entries)
    merged = json.loads(settings.read_text())
    agentboard_entries = [
        e
        for e in merged["hooks"]["UserPromptSubmit"]
        if e.get("_source") == "agentboard"
    ]
    assert len(agentboard_entries) == 1


def test_write_user_hooks_reinstall_preserves_foreign_entries(tmp_path: Path) -> None:
    # FM5: idempotent reinstall must not sweep away OTHER plugins' entries.
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": "other-plugin.sh"}]}
                    ]
                }
            }
        )
    )
    entries = {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "agentboard-hook.sh"}]}
        ]
    }
    install.write_user_hooks(settings, entries)
    install.write_user_hooks(settings, entries)
    merged = json.loads(settings.read_text())
    commands = [
        e["hooks"][0]["command"] for e in merged["hooks"]["UserPromptSubmit"]
    ]
    assert "other-plugin.sh" in commands
    assert commands.count("agentboard-hook.sh") == 1
