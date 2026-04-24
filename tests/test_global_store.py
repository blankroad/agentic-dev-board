"""GlobalStore — Tier 1/2 dual-write facade over ~/.agentboard/.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 — Cross-Project Memory.
"""

import json
import stat
from pathlib import Path

from agentboard.storage import global_store


def test_init_creates_global_dir_with_mode_0700_when_absent(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    global_store.GlobalStore()
    target = fake_home / ".agentboard"
    assert target.is_dir()
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_write_session_md_populates_date_sid_path(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    store = global_store.GlobalStore()
    written = store.write_session_md(
        session_id="abc123", date="2026-04-24", content="hello world"
    )
    expected = fake_home / ".agentboard" / "sessions" / "2026-04-24" / "abc123" / "session.md"
    assert written == expected
    assert expected.read_text() == "hello world"


def test_write_decision_applies_dedup_and_drops_duplicate(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    store = global_store.GlobalStore()
    key = dict(
        source="hook",
        session_id="s1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=100,
    )
    first = store.write_decision({"kind": "tool_use", "payload": 1}, **key)
    second = store.write_decision({"kind": "tool_use", "payload": 2}, **key)
    assert first is True
    assert second is False
    jsonl_path = fake_home / ".agentboard" / "decisions.jsonl"
    assert len(jsonl_path.read_text().splitlines()) == 1


def test_write_decision_tier1_mirrors_to_project_local_decisions(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    project_root = tmp_path / "proj"
    (project_root / ".agentboard").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    store = global_store.GlobalStore(project_root=project_root)
    store.write_decision(
        {"kind": "tool_use", "payload": "hello"},
        source="mcp",
        session_id="s-tier1",
        tool_call_seq=1,
        tool_name="Bash",
        args_json="{}",
        ts_bucket=1,
    )
    mirror = project_root / ".agentboard" / "decisions.jsonl"
    assert mirror.is_file()
    lines = mirror.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["payload"] == "hello"
