"""Unit tests for devboard.tui.goal_tree.build_goal_tree.

Covers atomic_steps s_007..s_013 from goal g_20260420_054657_bae0a8
(TUI goal panel hierarchy).

build_goal_tree is a PURE function:
    (goals: list[dict], show_archived: bool) -> list[tuple[dict, int]]

- filters status in {pushed, archived} unless show_archived=True
- promotes orphans (child whose parent is hidden) to depth=0
- sorts roots by created_at descending (newest first)
- falls back to id timestamp prefix when created_at missing
- returns DFS-flattened [(goal, depth), ...]
"""
from __future__ import annotations

from devboard.tui.goal_tree import build_goal_tree


def _g(id: str, *, title: str = "", status: str = "active",
       parent_id: str | None = None, created_at: str | None = None) -> dict:
    d: dict = {"id": id, "title": title or id, "status": status, "parent_id": parent_id}
    if created_at is not None:
        d["created_at"] = created_at
    return d


def test_build_goal_tree_roots_only() -> None:
    """s_007: two roots → returned flattened at depth=0."""
    goals = [
        _g("g_a", created_at="2026-04-18T00:00:00+00:00"),
        _g("g_b", created_at="2026-04-19T00:00:00+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=False)
    assert {g["id"] for g, _ in out} == {"g_a", "g_b"}
    assert all(depth == 0 for _, depth in out)


def test_build_goal_tree_roots_sorted_desc() -> None:
    """s_008: root goals sorted by created_at descending."""
    goals = [
        _g("g_old", created_at="2026-04-10T00:00:00+00:00"),
        _g("g_new", created_at="2026-04-20T00:00:00+00:00"),
        _g("g_mid", created_at="2026-04-15T00:00:00+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=False)
    assert [g["id"] for g, _ in out] == ["g_new", "g_mid", "g_old"]


def test_build_goal_tree_filters_completed() -> None:
    """s_009: show_archived=False drops status in {pushed, archived}."""
    goals = [
        _g("g_active", status="active", created_at="2026-04-18T00:00:00+00:00"),
        _g("g_pushed", status="pushed", created_at="2026-04-19T00:00:00+00:00"),
        _g("g_archived", status="archived", created_at="2026-04-20T00:00:00+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=False)
    assert {g["id"] for g, _ in out} == {"g_active"}


def test_build_goal_tree_show_archived_true() -> None:
    """s_010: show_archived=True keeps pushed/archived goals."""
    goals = [
        _g("g_active", status="active", created_at="2026-04-18T00:00:00+00:00"),
        _g("g_pushed", status="pushed", created_at="2026-04-19T00:00:00+00:00"),
        _g("g_archived", status="archived", created_at="2026-04-20T00:00:00+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=True)
    assert {g["id"] for g, _ in out} == {"g_active", "g_pushed", "g_archived"}


def test_build_goal_tree_orphan_promotion() -> None:
    """s_011: child with hidden parent is promoted to root depth=0.

    Edge category: orphan-promote. Covers the case where a parent gets
    archived/pushed (or toggled off), the child must still be reachable,
    not silently dropped.
    """
    # guards: widgets-need-reactive-hook-not-compose-once (orphan visibility)
    goals = [
        _g("g_parent", status="pushed", created_at="2026-04-10T00:00:00+00:00"),
        _g("g_child", status="active", parent_id="g_parent",
           created_at="2026-04-20T00:00:00+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=False)
    assert len(out) == 1
    child, depth = out[0]
    assert child["id"] == "g_child"
    assert depth == 0


def test_build_goal_tree_missing_created_at_fallback() -> None:
    """s_012: missing created_at falls back to id's timestamp prefix.

    id format: g_YYYYMMDD_HHMMSS_XXXXXX. Sorting by id prefix yields
    stable chronological order without crashing on KeyError.
    """
    goals = [
        _g("g_20260410_000000_aaaaaa"),  # no created_at
        _g("g_20260420_000000_bbbbbb"),  # no created_at
    ]
    out = build_goal_tree(goals, show_archived=False)
    ids = [g["id"] for g, _ in out]
    assert ids == ["g_20260420_000000_bbbbbb", "g_20260410_000000_aaaaaa"]


def test_build_goal_tree_dfs_depth() -> None:
    """s_013: parent depth=0, two children depth=1 contiguously (DFS)."""
    goals = [
        _g("g_parent", created_at="2026-04-20T00:00:00+00:00"),
        _g("g_child_b", parent_id="g_parent",
           created_at="2026-04-19T00:00:00+00:00"),
        _g("g_child_a", parent_id="g_parent",
           created_at="2026-04-18T00:00:00+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=False)
    assert [g["id"] for g, _ in out] == ["g_parent", "g_child_b", "g_child_a"]
    assert [d for _, d in out] == [0, 1, 1]


# ── redteam regression guards (tree-render-must-guard-cycles-and-dup-ids) ───

def test_build_goal_tree_tolerates_duplicate_id_self_parent() -> None:
    """Redteam CRITICAL: dup id + self-parent previously triggered
    RecursionError in _walk. Must terminate with no crash.
    """
    # guards: tree-render-must-guard-cycles-and-dup-ids
    goals = [
        _g("A", created_at="2026-04-20T00:00:00+00:00"),
        _g("B", parent_id="A", created_at="2026-04-20T00:00:01+00:00"),
        _g("B", parent_id="B", created_at="2026-04-20T00:00:02+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=False)
    # No crash. Exact membership is unspecified (dedupe policy) — we only
    # require termination and that every returned goal has a bounded depth.
    assert all(depth < 100 for _, depth in out)


def test_build_goal_tree_promotes_self_parent_to_root() -> None:
    """Redteam HIGH: a goal whose parent_id equals its own id must not
    silently vanish from the sidebar — orphan-promote semantics apply.
    """
    # guards: tree-render-must-guard-cycles-and-dup-ids
    goals = [_g("g_self", parent_id="g_self",
                created_at="2026-04-20T00:00:00+00:00")]
    out = build_goal_tree(goals, show_archived=False)
    assert len(out) == 1
    goal, depth = out[0]
    assert goal["id"] == "g_self"
    assert depth == 0


def test_build_goal_tree_promotes_two_cycle_members_to_root() -> None:
    """Redteam HIGH: 2-cycle A<->B previously hid both goals from the
    sidebar. At minimum both must appear in the output so the user can
    see and repair the damaged state."""
    # guards: tree-render-must-guard-cycles-and-dup-ids
    goals = [
        _g("A", parent_id="B", created_at="2026-04-20T00:00:00+00:00"),
        _g("B", parent_id="A", created_at="2026-04-20T00:00:01+00:00"),
    ]
    out = build_goal_tree(goals, show_archived=False)
    ids = {g["id"] for g, _ in out}
    assert ids == {"A", "B"}
