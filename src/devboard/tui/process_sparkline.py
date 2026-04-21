"""Process sparkline — two Sparkline widgets side by side:
  - iterations per hour (last 24 hours, fixed 1h buckets)
  - iron-law violation events per hour

Wrapper compute helper `build_series` returns (iter_hist, ironlaw_hist).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from textual.containers import Vertical
from textual.widgets import Sparkline, Static

BUCKETS: int = 24  # 1-hour buckets, 24-hour window


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        # accept both "...Z" and offset-aware ISO
        text = str(raw).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def build_series(decisions: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    """Return (iter_per_hour, ironlaw_per_hour) as 24-bucket lists indexed
    by hours-ago-from-now (index 0 = current hour).

    Empty input → two lists of 24 zeros.
    """
    iter_hist = [0] * BUCKETS
    ironlaw_hist = [0] * BUCKETS
    now = datetime.now(timezone.utc)
    for row in decisions:
        ts = _parse_ts(row.get("ts"))
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hours_ago = int((now - ts).total_seconds() // 3600)
        if not 0 <= hours_ago < BUCKETS:
            continue
        idx = BUCKETS - 1 - hours_ago  # oldest left, newest right
        phase = str(row.get("phase") or "")
        if phase.startswith("tdd_green"):
            iter_hist[idx] += 1
        if phase == "iron_law":
            ironlaw_hist[idx] += 1
    return iter_hist, ironlaw_hist


class ProcessSparkline(Vertical):
    """Mounts two Sparkline widgets: iter-rate on top, iron-law on bottom."""

    def __init__(self, decisions: list | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._decisions = decisions or []

    def compose(self):
        iter_hist, iron_hist = build_series(self._decisions)
        yield Static("iter/hr")
        yield Sparkline(iter_hist, id="process-sparkline-iter")
        yield Static("iron-law/hr")
        yield Sparkline(iron_hist, id="process-sparkline-iron")

    def refresh_render(self, decisions: list | None = None) -> None:
        if decisions is not None:
            self._decisions = decisions
        iter_hist, iron_hist = build_series(self._decisions)
        try:
            self.query_one("#process-sparkline-iter", Sparkline).data = iter_hist
            self.query_one("#process-sparkline-iron", Sparkline).data = iron_hist
        except Exception:
            # not mounted yet — next compose picks up fresh state
            pass
