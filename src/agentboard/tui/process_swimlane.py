"""Process swimlane — 6 phase lanes (gauntlet/tdd/review/cso/redteam/approval)
with one cell per event on the time axis.
"""

from __future__ import annotations

from textual.widgets import Static

LANE_ORDER: tuple[str, ...] = ("gauntlet", "tdd", "review", "cso", "redteam", "approval")
LANE_MATCHERS: dict[str, tuple[str, ...]] = {
    "gauntlet": ("gauntlet_complete", "plan", "eng_review"),
    "tdd": ("tdd_red", "tdd_green", "tdd_refactor"),
    "review": ("review", "parallel_review"),
    "cso": ("cso",),
    "redteam": ("redteam",),
    "approval": ("approval",),
}


def _match_lane(phase: str) -> str | None:
    for lane, needles in LANE_MATCHERS.items():
        if phase in needles:
            return lane
    # prefix match fallback (e.g. `tdd_green_carryover` → tdd)
    for lane, needles in LANE_MATCHERS.items():
        for needle in needles:
            if phase.startswith(needle):
                return lane
    return None


def render_swimlane(decisions: list[dict]) -> str:
    """Render a text swimlane. Each lane gets one row; each matching event
    places a `■` on the lane at its sequential slot position."""
    # Bucket events per lane in order of appearance
    per_lane: dict[str, list[dict]] = {lane: [] for lane in LANE_ORDER}
    for row in decisions:
        phase = str(row.get("phase") or "")
        lane = _match_lane(phase)
        if lane is not None:
            per_lane[lane].append(row)

    max_events = max((len(v) for v in per_lane.values()), default=0)
    lines: list[str] = []
    for lane in LANE_ORDER:
        events = per_lane[lane]
        slots = ["■" if i < len(events) else "─" for i in range(max(max_events, 1))]
        lines.append(f"{lane:<10}" + "".join(slots))
    return "\n".join(lines)


class ProcessSwimlane(Static):
    def __init__(self, decisions: list | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._decisions = decisions or []

    def refresh_render(self, decisions: list | None = None) -> None:
        if decisions is not None:
            self._decisions = decisions
        self.update(render_swimlane(self._decisions))

    def on_mount(self) -> None:
        self.refresh_render()
