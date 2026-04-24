"""Stop hook — finalizes Tier 2 session record on Claude Code exit.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §Data Flow —
GlobalStore.finalize_session writes a finalization marker so retro/replay
can distinguish clean-exit sessions from crashed ones.
"""

from datetime import date as _date
from pathlib import Path

from agentboard.hooks_py import session_start, stop


def test_stop_finalizes_session_record(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    session_start.main({"session_id": "abc", "hook_event_name": "SessionStart"})
    stop.main({"session_id": "abc", "hook_event_name": "Stop"})
    today = _date.today().isoformat()
    session_md = fake_home / ".agentboard" / "sessions" / today / "abc" / "session.md"
    assert "finalized: true" in session_md.read_text()
