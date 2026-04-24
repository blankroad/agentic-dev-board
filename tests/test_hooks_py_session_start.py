"""SessionStart hook — initializes Tier 2 ambient-capture session record.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §Data Flow — SessionStart
hook fires on every Claude Code session start and creates an empty session.md
under ~/.agentboard/sessions/<date>/<sid>/.
"""

from datetime import date as _date
from pathlib import Path

from agentboard.hooks_py import session_start


def test_session_start_creates_tier2_session_record(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    session_start.main({"session_id": "abc123", "hook_event_name": "SessionStart"})
    today = _date.today().isoformat()
    target = (
        fake_home / ".agentboard" / "sessions" / today / "abc123" / "session.md"
    )
    assert target.is_file()
