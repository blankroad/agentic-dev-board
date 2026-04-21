"""Responsive layout selector for Dev tab (M1b m_008).

Maps terminal column count to one of four named layouts. Locked spec
from /autoplan Phase 2 BLOCKER fix:

| cols     | layout |
|----------|--------|
| >= 120   | "3pane"  | File tree (25%) / Diff (55%) / Issues rail (20%)
| 100-119  | "2pane"  | File tree + Diff (rail collapsed to bottom row)
| 80-99    | "1pane"  | 1-pane + tab strip [Files] [Diff] [Findings]
| < 80     | "banner" | "terminal too narrow" placeholder
"""
from __future__ import annotations

from typing import Literal

from agentboard.tui.tui_tokens import (
    BREAKPOINT_1PANE,
    BREAKPOINT_2PANE,
    BREAKPOINT_3PANE,
)

LayoutName = Literal["3pane", "2pane", "1pane", "banner"]


def responsive_layout(cols: int) -> LayoutName:
    if cols >= BREAKPOINT_3PANE:
        return "3pane"
    if cols >= BREAKPOINT_2PANE:
        return "2pane"
    if cols >= BREAKPOINT_1PANE:
        return "1pane"
    return "banner"
