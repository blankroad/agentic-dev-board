from __future__ import annotations


_DETAIL_KEYS = (
    "iter",
    "iteration",
    "current_step_id",
    "status",
    "verdict",
    "test_file",
    "impl_file",
    "task_id",
    "run_id",
    "goal_id",
)


def format_event_line(record: object) -> str:
    """Convert a JSONL event dict to one compact human-readable line.

    Shape: `[HH:MM:SS] event_name           key=val key=val ...`

    Non-dict records and records missing fields degrade gracefully — this
    runs on every tail poll so it must never raise.
    """
    if not isinstance(record, dict):
        return str(record)[:120]

    ts = record.get("ts")
    if isinstance(ts, str) and "T" in ts:
        time_part = ts.split("T", 1)[1][:8]
    else:
        time_part = "--:--:--"

    event = str(record.get("event", "?"))

    state = record.get("state") if isinstance(record.get("state"), dict) else {}
    pairs: list[str] = []
    for key in _DETAIL_KEYS:
        if key in state:
            val = state[key]
            if not isinstance(val, (str, int, float, bool)):
                continue
            if isinstance(val, str) and len(val) > 32:
                val = val[:29] + "..."
            pairs.append(f"{key}={val}")
        if len(pairs) >= 4:
            break

    detail = " ".join(pairs)
    return f"[{time_part}] {event:<24} {detail}".rstrip()
