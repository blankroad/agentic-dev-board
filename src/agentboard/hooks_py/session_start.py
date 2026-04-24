"""SessionStart hook — initializes Tier 2 ambient-capture session record."""

from datetime import date as _date

from agentboard.storage.global_store import GlobalStore


def main(payload: dict) -> None:
    session_id = payload.get("session_id", "unknown")
    today = _date.today().isoformat()
    GlobalStore().init_tier2_session(session_id=session_id, date=today)
