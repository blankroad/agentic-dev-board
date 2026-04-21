"""Model-level tests for Goal.parent_id field.

Covers atomic_steps s_001, s_002, s_003 from goal
g_20260420_054657_bae0a8 (TUI goal panel hierarchy).
"""
from __future__ import annotations

import json

from agentboard.models import Goal


def test_goal_parent_id_default_none() -> None:
    """s_001: a freshly constructed Goal has parent_id == None."""
    goal = Goal(title="root goal")
    assert goal.parent_id is None


def test_goal_parent_id_roundtrip() -> None:
    """s_002: explicit parent_id survives JSON roundtrip."""
    # guards: mcp-required-field-check-must-reject-none (serialization side)
    g = Goal(title="child", parent_id="g_abc")
    raw = g.model_dump_json()
    restored = Goal.model_validate_json(raw)
    assert restored.parent_id == "g_abc"


def test_goal_legacy_json_without_parent_id_loads() -> None:
    """s_003: edge — legacy JSON without parent_id key loads with default None.

    Category: backward-compat. Existing .devboard/goals/*/goal.json files
    predate this field and must not crash on reload.
    """
    legacy = {
        "id": "g_legacy",
        "title": "legacy goal",
        "description": "",
        "status": "active",
        "branch_prefix": "",
        "task_ids": [],
        "locked_plan": None,
        "cost_tokens_used": 0,
        "created_at": "2026-04-18T01:40:50+00:00",
        "updated_at": "2026-04-18T01:40:50+00:00",
    }
    goal = Goal.model_validate_json(json.dumps(legacy))
    assert goal.parent_id is None
