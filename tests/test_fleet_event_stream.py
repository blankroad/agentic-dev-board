"""FleetEventStream tail-buffer tests (M2-fleet-tui s_005)."""
from __future__ import annotations


def test_fleet_event_stream_tail_cap() -> None:
    """s_005: push_event appends to buffer; cap at 12; oldest drops."""
    from agentboard.tui.fleet_event_stream import FleetEventStream, TAIL_CAP

    stream = FleetEventStream()
    assert TAIL_CAP == 12
    assert stream._events == []

    for i in range(15):
        stream.push_event(f"event-{i}", color=None)

    assert len(stream._events) == TAIL_CAP
    # oldest 3 dropped, newest remain
    assert stream._events[0][0] == "event-3"
    assert stream._events[-1][0] == "event-14"


def test_fleet_event_stream_push_with_color() -> None:
    """s_005: push_event preserves color tuple."""
    from agentboard.tui.fleet_event_stream import FleetEventStream

    stream = FleetEventStream()
    stream.push_event("hello", color="red")
    assert stream._events[-1] == ("hello", "red")
