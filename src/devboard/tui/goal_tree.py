"""Pure data transformation for the TUI goal sidebar.

Given a list of goal dicts (shape produced by SessionContext.all_goals),
produce a DFS-flattened list of (goal_dict, depth) rows respecting:

  * filter: drop goals whose status is in {pushed, archived} unless
    show_archived=True
  * orphan-promote: if a child's parent_id refers to a hidden/missing
    goal, the child is treated as a root (depth=0)
  * sort: roots are ordered by created_at descending (newest first);
    missing created_at falls back to the id's timestamp prefix
  * DFS: within a parent, children appear contiguously right after
    the parent in the output, sorted by the same key

This module is deliberately widget-free so it can be unit-tested without
a Textual App.
"""
from __future__ import annotations

from typing import Iterable

_HIDDEN_STATUSES = frozenset({"pushed", "archived"})


def _sort_key(goal: dict) -> str:
    """Sort by created_at if present, else fall back to the id's timestamp
    prefix (ids are formatted g_YYYYMMDD_HHMMSS_XXXXXX, which is
    lexicographically ordered)."""
    ca = goal.get("created_at")
    if isinstance(ca, str) and ca:
        return ca
    gid = goal.get("id", "")
    return gid[2:] if gid.startswith("g_") else gid


def build_goal_tree(
    goals: Iterable[dict],
    show_archived: bool,
) -> list[tuple[dict, int]]:
    goals = list(goals)

    if show_archived:
        visible = list(goals)
    else:
        visible = [g for g in goals if g.get("status") not in _HIDDEN_STATUSES]

    visible_ids = {g["id"] for g in visible}

    children_by_parent: dict[str | None, list[dict]] = {}
    for g in visible:
        pid = g.get("parent_id")
        # Orphan-promote a child to root when: (a) no parent, (b) parent is
        # hidden/missing, (c) parent_id equals the goal's own id (degenerate
        # self-cycle). 2-cycles and longer cycles are handled by the
        # visited guard in _walk.
        if pid is None or pid not in visible_ids or pid == g.get("id"):
            children_by_parent.setdefault(None, []).append(g)
        else:
            children_by_parent.setdefault(pid, []).append(g)

    for siblings in children_by_parent.values():
        siblings.sort(key=_sort_key, reverse=True)

    out: list[tuple[dict, int]] = []
    visited: set[str] = set()

    def _walk(parent_id: str | None, depth: int) -> None:
        for g in children_by_parent.get(parent_id, []):
            gid = g.get("id")
            if gid in visited:
                # Cycle or duplicate-id: emit once, do not descend again.
                continue
            visited.add(gid)
            out.append((g, depth))
            _walk(gid, depth + 1)

    _walk(None, 0)

    # Any node not reached from root (n-cycle among visible nodes where no
    # member was promoted) must still surface as root so the user can see
    # and repair the damaged state.
    for g in visible:
        gid = g.get("id")
        if gid not in visited:
            visited.add(gid)
            out.append((g, 0))

    return out
