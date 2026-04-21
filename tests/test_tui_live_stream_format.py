from __future__ import annotations


def test_format_event_line_pulls_hh_mm_ss_and_event() -> None:
    from agentboard.tui.live_stream_format import format_event_line

    record = {
        "ts": "2026-04-18T08:38:34.602963+00:00",
        "event": "run_start",
        "state": {"run_id": "run_108d830b", "goal_id": "g_abc"},
    }
    line = format_event_line(record)
    assert "08:38:34" in line, line
    assert "run_start" in line, line


def test_format_event_line_tdd_green_shows_iter_and_status() -> None:
    from agentboard.tui.live_stream_format import format_event_line

    record = {
        "ts": "2026-04-18T08:39:31+00:00",
        "event": "tdd_green_complete",
        "state": {
            "iteration": 3,
            "current_step_id": "s_007",
            "status": "GREEN_CONFIRMED",
        },
    }
    line = format_event_line(record)
    assert "tdd_green_complete" in line, line
    assert "iter=3" in line or "iteration=3" in line, line
    assert "GREEN" in line, line


def test_format_event_line_tolerates_missing_fields() -> None:
    from agentboard.tui.live_stream_format import format_event_line

    # No ts, no state — must not crash
    assert "mystery" in format_event_line({"event": "mystery"})
    # Non-dict record
    assert format_event_line("not a dict") != ""
    assert format_event_line({}) != ""
