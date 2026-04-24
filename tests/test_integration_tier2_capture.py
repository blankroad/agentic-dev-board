"""Goal checklist #1 — non-init cwd fake Claude Code session leaves a
populated session.md under ~/.agentboard/sessions/<date>/<sid>/.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 goal_checklist item 1.
"""

from datetime import date as _date
from pathlib import Path


def test_fake_session_populates_session_md_in_non_init_cwd(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    from agentboard.hooks_py import post_tool_use, session_start, stop

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    # Non-init cwd: a directory with no .agentboard/ — Tier 2 ambient scenario.
    (tmp_path / "random-dir").mkdir()

    session_start.main({"session_id": "fake-sid", "hook_event_name": "SessionStart"})
    post_tool_use.main(
        {
            "session_id": "fake-sid",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_call_seq": 1,
            "ts_bucket": 1,
        }
    )
    stop.main({"session_id": "fake-sid", "hook_event_name": "Stop"})

    today = _date.today().isoformat()
    session_md = (
        fake_home / ".agentboard" / "sessions" / today / "fake-sid" / "session.md"
    )
    assert session_md.is_file()
    content = session_md.read_text().strip()
    assert content != ""
    assert "finalized: true" in content
