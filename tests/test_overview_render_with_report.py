"""Phase A/B tests — report.md integration into overview_payload + overview_render.

s_001: payload has 'report_md' key (empty when file absent)
s_002: payload.report_md reads file contents when present
s_003: render_overview_body prepends report_md content when non-empty
s_004: render_overview_body preserves legacy layout when report_md empty
"""

from __future__ import annotations

from pathlib import Path


def _bootstrap(tmp_path: Path, task_id: str | None = "t_r") -> str:
    """Minimal goal + plan fixture. Returns goal_id."""
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".agentboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_rep")
    board.goals.append(Goal(id="g_rep", title="report-fixture", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".agentboard" / "goals" / "g_rep"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# plan\n")
    if task_id:
        import json as _json

        task_dir = goal_dir / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(_json.dumps({"id": task_id, "status": "pushed"}))
    return "g_rep"


def test_render_no_duplicate_purpose_header_when_report_contains_one() -> None:
    """redteam FM#6 — when payload.report_md already carries a '## 목적'
    heading (common — LLM copies visible Korean section names), the
    renderer must NOT emit the legacy '## 목적 (Purpose)' a second time
    below. The output should contain '## 목적' at most from the AI report."""
    from agentboard.tui.overview_render import render_overview_body

    report_md_with_purpose = (
        "## 목적\n\n이 goal의 목적 요약.\n\n"
        "## 변화 지표\n| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    )
    payload = {
        "report_md": report_md_with_purpose,
        "purpose": "legacy-purpose",
        "plan_digest": {"locked_hash": "x", "scope_decision": "HOLD",
                        "atomic_steps_total": 1, "atomic_steps_done": 0},
        "iterations": [],
        "current_state": {"status": "pushed"},
    }
    out = render_overview_body(payload)
    # Count '## 목적' occurrences — must be 1 (from report_md only),
    # NOT 2 (report_md + legacy plan_digest block).
    count = out.count("## 목적")
    assert count == 1, (
        f"'## 목적' should appear exactly once when report_md already has it; "
        f"got {count} occurrences. Output:\n{out}"
    )


def test_render_preserves_legacy_layout_when_report_empty() -> None:
    """s_004 — when payload.report_md is empty, the legacy plan_digest
    layout ('## 목적' → '## 계획 요약' → '## 활동' → '## 현재 상태') must
    appear with '## 목적' as the top-most section (backward compat)."""
    from agentboard.tui.overview_render import render_overview_body

    payload = {
        "report_md": "",
        "purpose": "legacy-purpose",
        "plan_digest": {
            "locked_hash": "abc",
            "scope_decision": "HOLD",
            "atomic_steps_total": 3,
            "atomic_steps_done": 0,
        },
        "iterations": [],
        "current_state": {"status": "pushed"},
    }
    out = render_overview_body(payload)
    # '## 목적' must be at the top (no preceding section header).
    head = out.split("\n", 1)[0]
    assert head == "## 목적 (Purpose)", (
        f"when report_md empty, first line must be '## 목적 (Purpose)' "
        f"(legacy layout); got: {head!r}"
    )


def test_render_prepends_report_md_when_present() -> None:
    """s_003 — render_overview_body must emit payload.report_md at the
    very top when it is non-empty, so Overview tab leads with the human-
    readable summary instead of hash/plan_digest."""
    from agentboard.tui.overview_render import render_overview_body

    sentinel = "SENTINEL_REPORT_HEADER_X7Q"
    payload = {
        "report_md": f"## {sentinel}\n\n본문 요약.\n",
        "purpose": "purpose-sentinel",
        "plan_digest": {
            "locked_hash": "abc",
            "scope_decision": "HOLD",
            "atomic_steps_total": 3,
            "atomic_steps_done": 0,
        },
        "iterations": [],
        "current_state": {"status": "pushed"},
    }
    out = render_overview_body(payload)
    assert sentinel in out, (
        f"report_md sentinel must appear in render output; body:\n{out}"
    )
    # Verify ordering: sentinel appears BEFORE the legacy '목적' header.
    sentinel_idx = out.find(sentinel)
    legacy_idx = out.find("## 목적")
    assert sentinel_idx >= 0 and legacy_idx >= 0, (
        f"both markers expected; sentinel={sentinel_idx} legacy={legacy_idx}"
    )
    assert sentinel_idx < legacy_idx, (
        f"report_md must render BEFORE legacy plan_digest ('## 목적'); "
        f"got sentinel@{sentinel_idx} legacy@{legacy_idx}"
    )


def test_payload_report_md_reads_file_contents(tmp_path: Path) -> None:
    """s_002 — when .agentboard/goals/<gid>/report.md exists, its content
    must land verbatim in payload.report_md."""
    from agentboard.analytics.overview_payload import build_overview_payload

    goal_id = _bootstrap(tmp_path)
    report_body = (
        "## 이 goal은 무엇을 개선했나\n\n"
        "테스트 목적의 요약 본문입니다.\n\n"
        "## 변화 지표\n\n"
        "| 영역 | As-Is | To-Be |\n"
        "| --- | --- | --- |\n"
        "| 예시 | 이전 | 이후 |\n"
    )
    (tmp_path / ".agentboard" / "goals" / goal_id / "report.md").write_text(
        report_body, encoding="utf-8"
    )
    payload = build_overview_payload(tmp_path, goal_id, task_id="t_r")
    assert payload["report_md"] == report_body, (
        f"payload.report_md must match file contents verbatim; "
        f"got {payload['report_md']!r}"
    )


def test_payload_includes_empty_report_md_when_file_absent(tmp_path: Path) -> None:
    """s_001 — payload must always carry a 'report_md' key; defaults to ''
    when .agentboard/goals/<gid>/report.md does not exist."""
    from agentboard.analytics.overview_payload import build_overview_payload

    goal_id = _bootstrap(tmp_path)
    payload = build_overview_payload(tmp_path, goal_id, task_id="t_r")
    assert "report_md" in payload, (
        f"payload must include 'report_md' key even when file absent; "
        f"got keys: {sorted(payload.keys())}"
    )
    assert payload["report_md"] == "", (
        f"expected empty report_md when file absent, got {payload['report_md']!r}"
    )
