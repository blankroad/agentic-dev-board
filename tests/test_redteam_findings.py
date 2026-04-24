"""Red-team regression tests for goal g_20260424_035650_6ecdd2.

These tests reproduce the three attack scenarios flagged by agentboard-redteam
at the post-execute gate. Each test is RED until the corresponding hardening
ships. They encode the spec guarantees that the post-merge implementation
must restore.
"""

import json
import tempfile
from pathlib import Path


def test_attack1_empty_prompt_must_not_inject_unrelated_learnings(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    # HIGH — empty/whitespace prompt must produce EMPTY output, not top-K noise.
    from agentboard.hooks_py import user_prompt_submit
    from agentboard.storage.global_index import GlobalIndex

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    idx = GlobalIndex()
    idx.register_learning(
        fake_home / "proj",
        {"name": "unrelated-1", "content": "totally irrelevant alpha", "tags": ["x"]},
    )
    output = user_prompt_submit.main({"prompt": ""})
    assert output == "", (
        "Empty prompt should produce no injection; "
        f"got: {output!r}"
    )


def test_attack2_concurrent_globalstore_writes_must_dedup_to_one_entry(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    # CRITICAL — arch.md edge_case #2 explicitly requires fcntl.flock(LOCK_EX)
    # so concurrent writers cannot double-append. Current impl builds _decision_keys
    # in-memory at __init__; two instances initialized before either writes both
    # see empty state and the second write bypasses dedup.
    from agentboard.storage.global_store import GlobalStore

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    a = GlobalStore()
    b = GlobalStore()  # both init before any write — simulates two processes
    key = dict(
        source="user_hook",
        session_id="s-race",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=1,
    )
    a.write_decision({"kind": "tool_use", "by": "A"}, **key)
    b.write_decision({"kind": "tool_use", "by": "B"}, **key)
    lines = (fake_home / ".agentboard" / "decisions.jsonl").read_text().splitlines()
    assert len(lines) == 1, (
        f"goal_checklist #4 requires exactly 1 entry under concurrent writers; "
        f"got {len(lines)} — arch.md fcntl.flock(LOCK_EX) requirement violated."
    )


def test_attack3_write_user_hooks_must_survive_malformed_settings(
    tmp_path: Path,
) -> None:
    # MEDIUM — settings.json may be partially-written / corrupted. Install must
    # not crash the flow; a recoverable degradation (warn + initialize fresh,
    # or leave existing corrupt content intact) is acceptable, but unhandled
    # JSONDecodeError that aborts the installer is not.
    from agentboard import install

    settings = tmp_path / "settings.json"
    settings.write_text('{ "hooks": {"PostToolUse": [')
    # If this raises, the attack succeeds.
    install.write_user_hooks(
        settings,
        {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "x"}]}]},
    )
    # After the call, settings.json should be valid JSON (either healed or
    # replaced) so the NEXT install cycle can proceed.
    json.loads(settings.read_text())


def test_attackB_write_user_hooks_survives_hooks_as_list(tmp_path: Path) -> None:
    # MEDIUM round-2 — valid JSON with wrong-schema `hooks` as list, not dict.
    from agentboard import install

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": [1, 2, 3]}))
    install.write_user_hooks(
        settings,
        {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "x"}]}]},
    )
    merged = json.loads(settings.read_text())
    # Install must recover — agentboard entry must land in a dict-shaped hooks.
    assert isinstance(merged.get("hooks"), dict)
    assert (
        merged["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "x"
    )


def test_attackE_user_prompt_submit_survives_none_prompt(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    # MEDIUM round-2 — payload with explicit `"prompt": None` (Claude Code
    # runtime may occasionally serialize missing prompts as null).
    from agentboard.hooks_py import user_prompt_submit

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    output = user_prompt_submit.main({"prompt": None})
    assert output == ""


def test_attackC_resolve_tier_survives_unreadable_ignore_paths(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    # MEDIUM round-2 — ignore_paths.txt exists but is unreadable (mode 0o000).
    # arch.md edge #11 style: fail-closed on read, continue without crash.
    from agentboard.storage import path_filter

    fake_home = tmp_path / "home"
    (fake_home / ".agentboard").mkdir(parents=True)
    ignore_file = fake_home / ".agentboard" / "ignore_paths.txt"
    ignore_file.write_text("/opt/secret\n")
    ignore_file.chmod(0o000)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    try:
        # Classification proceeds as if ignore_paths didn't exist — returns tier2
        # for a generic /tmp path.
        assert path_filter.resolve_tier(Path("/tmp/foo")) == "tier2"
    finally:
        ignore_file.chmod(0o644)  # restore so tmp cleanup works
