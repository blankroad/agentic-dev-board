from __future__ import annotations

import json
from pathlib import Path

import pytest


def _mk_goal(
    tmp_path: Path,
    gid: str,
    title: str,
    task_status: str | None = None,
    parent_id: str | None = None,
    status: str = "active",
) -> None:
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir(exist_ok=True)
    store = FileStore(tmp_path)
    try:
        board = store.load_board()
    except Exception:
        board = BoardState()
    board.goals.append(
        Goal(id=gid, title=title, status=GoalStatus(status), parent_id=parent_id)
    )
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / gid
    goal_dir.mkdir(parents=True, exist_ok=True)
    (goal_dir / "plan.md").write_text("# p\n")
    if task_status:
        task_dir = goal_dir / "tasks" / f"t_{gid}"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps({"id": f"t_{gid}", "status": task_status})
        )


async def _mount(tmp_path: Path):
    from textual.app import App, ComposeResult

    from agentboard.tui.goal_side_list import GoalSideList
    from agentboard.tui.session_derive import SessionContext

    ctx = SessionContext(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield GoalSideList(ctx, id="gsl")

    return _Host()


@pytest.mark.asyncio
async def test_goal_side_list_renders_all_goals_with_markers(tmp_path: Path) -> None:
    _mk_goal(tmp_path, "g_shipped", "shipped-goal", task_status="pushed")
    _mk_goal(tmp_path, "g_wip", "wip-goal", task_status="in_progress")
    app = await _mount(tmp_path)
    async with app.run_test(size=(40, 20)) as pilot:
        await pilot.pause()
        lv = app.query_one("#resources-goals")
        texts = []
        for item in lv.children:
            try:
                texts.append(str(item.query_one("Label").render()))
            except Exception:
                pass
        joined = " | ".join(texts)
        assert "shipped-goal" in joined, joined
        assert "wip-goal" in joined, joined
        # Markers differ between pushed and wip
        shipped_line = next(t for t in texts if "shipped-goal" in t)
        wip_line = next(t for t in texts if "wip-goal" in t)
        assert shipped_line.split("shipped-goal")[0] != wip_line.split("wip-goal")[0]


@pytest.mark.asyncio
async def test_goal_side_list_markers_are_colored(tmp_path: Path) -> None:
    """Each status marker (✓/●/▶/✗/○/?/·) should render with a distinct
    color via Rich markup so the user can scan status at a glance without
    reading labels."""
    _mk_goal(tmp_path, "g_shipped", "shipped", task_status="pushed")
    _mk_goal(tmp_path, "g_wip", "wip", task_status="in_progress")
    _mk_goal(tmp_path, "g_blocked", "blocked-g", task_status="blocked")
    app = await _mount(tmp_path)
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        lv = app.query_one("#resources-goals")
        # Collect rendered span styles from each item's Label
        styled_colors: set[str] = set()
        for item in lv.children:
            try:
                label = item.query_one("Label")
            except Exception:
                continue
            rendered = label.render()
            spans = getattr(rendered, "spans", [])
            for s in spans:
                style = str(getattr(s, "style", ""))
                styled_colors.add(style.lower())
        flat = " ".join(styled_colors)
        # at least green (pushed), blue/yellow (wip), red (blocked) must
        # appear somewhere in the rendered styles
        assert "green" in flat, f"pushed marker should have green; styles={flat!r}"
        assert "red" in flat, f"blocked marker should have red; styles={flat!r}"


@pytest.mark.asyncio
async def test_goal_side_list_shows_inline_legend(tmp_path: Path) -> None:
    _mk_goal(tmp_path, "g1", "one", task_status="pushed")
    app = await _mount(tmp_path)
    async with app.run_test(size=(40, 20)) as pilot:
        await pilot.pause()
        legend = app.query_one("#goal-side-legend")
        text = str(legend.render())
        assert "✓" in text and "▶" in text and "✗" in text, (
            f"inline legend missing markers: {text!r}"
        )


# ── hierarchy + archived toggle (goal g_20260420_054657_bae0a8) ──────────────

def test_goal_side_list_has_toggle_archived_binding() -> None:
    """s_014: GoalSideList.BINDINGS exposes the 'a' key bound to
    action 'toggle_archived' so users can reveal completed goals."""
    from agentboard.tui.goal_side_list import GoalSideList

    bindings = getattr(GoalSideList, "BINDINGS", [])
    hit = False
    for b in bindings:
        # textual bindings may be a Binding dataclass or a tuple
        key = getattr(b, "key", None) or (b[0] if isinstance(b, tuple) else None)
        action = getattr(b, "action", None) or (
            b[1] if isinstance(b, tuple) and len(b) > 1 else None
        )
        if key == "a" and action == "toggle_archived":
            hit = True
            break
    assert hit, f"missing ('a', 'toggle_archived') binding; got {bindings!r}"


@pytest.mark.asyncio
async def test_goal_side_list_toggle_archived_flips_state(tmp_path: Path) -> None:
    """s_015: action_toggle_archived flips _show_archived AND re-renders.

    Guards: widgets-need-reactive-hook-not-compose-once — state flip alone
    is not enough; the list must reflect the new filter after the action.
    """
    # guards: widgets-need-reactive-hook-not-compose-once
    _mk_goal(tmp_path, "g_wip", "wip-goal", task_status="in_progress")
    _mk_goal(tmp_path, "g_done", "done-goal", status="pushed", task_status="pushed")
    app = await _mount(tmp_path)
    async with app.run_test(size=(40, 20)) as pilot:
        await pilot.pause()
        from agentboard.tui.goal_side_list import GoalSideList

        gsl = app.query_one(GoalSideList)
        assert gsl._show_archived is False

        def _labels() -> list[str]:
            lv = app.query_one("#resources-goals")
            out: list[str] = []
            for item in lv.children:
                try:
                    out.append(str(item.query_one("Label").render()))
                except Exception:
                    pass
            return out

        before = _labels()
        assert any("wip-goal" in t for t in before)
        assert not any("done-goal" in t for t in before), (
            f"pushed goal should be hidden initially: {before!r}"
        )

        gsl.action_toggle_archived()
        await pilot.pause()

        assert gsl._show_archived is True
        after = _labels()
        assert any("done-goal" in t for t in after), (
            f"toggle did not re-render pushed goal into the list: {after!r}"
        )


@pytest.mark.asyncio
async def test_goal_side_list_renders_child_with_indent(tmp_path: Path) -> None:
    """s_016: child goals are rendered with a leading indent when their
    parent is visible in the tree."""
    _mk_goal(tmp_path, "g_parent", "parent-goal", task_status="in_progress")
    _mk_goal(
        tmp_path, "g_child", "child-goal",
        parent_id="g_parent", task_status="in_progress",
    )
    app = await _mount(tmp_path)
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        lv = app.query_one("#resources-goals")
        child_label: str | None = None
        parent_label: str | None = None
        for item in lv.children:
            try:
                text = str(item.query_one("Label").render())
            except Exception:
                continue
            if "child-goal" in text:
                child_label = text
            elif "parent-goal" in text:
                parent_label = text
        assert parent_label is not None, "parent goal missing from list"
        assert child_label is not None, "child goal missing from list"
        # Child label must start with visible indent spaces before its marker.
        # Parent has no indent — so child's pre-title prefix is longer.
        parent_prefix = parent_label.split("parent-goal")[0]
        child_prefix = child_label.split("child-goal")[0]
        assert len(child_prefix) > len(parent_prefix), (
            f"child should be indented deeper than parent; "
            f"parent_prefix={parent_prefix!r}, child_prefix={child_prefix!r}"
        )
