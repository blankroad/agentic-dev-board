"""Tests for render_dev_timeline (s_009)."""

from agentboard.tui.dev_timeline_render import render_dev_timeline


def test_render_dev_timeline_iter_block_oldest_top() -> None:
    payload = {
        "iterations": [
            {"iter": 1, "phase": "tdd_red", "verdict": "RED_CONFIRMED",
             "ts": "2026-04-20T13:30:00", "touched_files": ["tests/x.py"],
             "diff_stats": {"adds": 3, "dels": 0}},
            {"iter": 2, "phase": "tdd_green", "verdict": "GREEN_CONFIRMED",
             "ts": "2026-04-20T13:38:00", "touched_files": ["src/x.py"],
             "diff_stats": {"adds": 15, "dels": 2}},
        ],
    }
    out = render_dev_timeline(payload)
    assert "iter 1" in out
    assert "iter 2" in out
    # oldest-top invariant: iter 1 appears before iter 2
    assert out.index("iter 1") < out.index("iter 2")
    assert "tests/x.py" in out
    assert "src/x.py" in out
    assert "+15" in out and "−2" in out


def test_render_dev_timeline_empty() -> None:
    assert "활동 없음" in render_dev_timeline({"iterations": []})
