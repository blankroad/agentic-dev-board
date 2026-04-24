"""Stop hook — finalizes Tier 2 session record on clean Claude Code exit."""

from datetime import date as _date

from agentboard.storage.global_store import GlobalStore


def main(payload: dict) -> None:
    session_id = payload.get("session_id", "unknown")
    today = _date.today().isoformat()
    GlobalStore().finalize_session(session_id=session_id, date=today)
