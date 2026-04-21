"""Phase A tests — overview_payload cross-ref correctness.

Covers:
- s_002: iterations[i].step_id (regex priority over index)
- s_003: iterations[i] cross-ref fields (behavior/test_file/test_name/impl_file)
- s_004: step_shipping computed from decisions.jsonl tdd_green
- s_006: risk_delta cross-ref (challenge × completed steps × parallel_review)
"""

from __future__ import annotations

import json
from pathlib import Path


def _bootstrap_task_with_plan(
    tmp_path: Path,
    *,
    atomic_steps: list[dict] | None = None,
    decisions: list[dict] | None = None,
    task_status: str = "in_progress",
) -> tuple[str, str]:
    """Create a goal + task + plan.json + decisions.jsonl fixture.
    Returns (goal_id, task_id)."""
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_s")
    board.goals.append(Goal(id="g_s", title="fx", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_s"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# plan\n")
    steps = atomic_steps or [
        {
            "id": "s_001",
            "behavior": "overview tab wraps VerticalScroll",
            "test_file": "tests/test_tui_center_scroll.py",
            "test_name": "test_overview_tab_wraps_static_in_vertical_scroll",
            "impl_file": "src/agentboard/tui/phase_flow.py",
        },
        {
            "id": "s_002",
            "behavior": "all five tabs wrap body",
            "test_file": "tests/test_tui_center_scroll.py",
            "test_name": "test_all_five_tabs_wrap_body_in_vertical_scroll",
            "impl_file": "src/agentboard/tui/phase_flow.py",
        },
        {
            "id": "s_003",
            "behavior": "down key scrolls",
            "test_file": "tests/test_tui_center_scroll.py",
            "test_name": "test_down_key_scrolls_plan_viewport",
            "impl_file": "src/agentboard/tui/phase_flow.py",
        },
    ]
    (goal_dir / "plan.json").write_text(json.dumps({"atomic_steps": steps}))
    task_dir = goal_dir / "tasks" / "t_s"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(
        json.dumps({"id": "t_s", "status": task_status})
    )
    decs = decisions or [
        {"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "s_001 GREEN: wrap overview in VerticalScroll", "ts": "2026-04-20T10:00:00+00:00"},
        {"iter": 2, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "s_002: plan/dev/result/review tabs wrapped", "ts": "2026-04-20T10:01:00+00:00"},
        {"iter": 3, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "s_003 critical-path check already satisfied", "ts": "2026-04-20T10:02:00+00:00"},
    ]
    (task_dir / "decisions.jsonl").write_text(
        "\n".join(json.dumps(d) for d in decs) + "\n"
    )
    return "g_s", "t_s"


def test_step_shipping_from_decisions_jsonl_tdd_green(tmp_path: Path) -> None:
    """s_004 — payload.step_shipping[*].shipped must be True for every
    atomic_step whose id appears in a tdd_green decision row's reasoning.
    Previously relied on plan.json.completed (never set → always 0)."""
    from agentboard.analytics.overview_payload import build_overview_payload

    # 3 atomic_steps, but only s_001 and s_003 have tdd_green with matching
    # reasoning. s_002 must stay shipped=False.
    decisions = [
        {"iter": 1, "phase": "tdd_red", "verdict_source": "RED_CONFIRMED",
         "reasoning": "s_001 RED: structure check"},
        {"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "s_001 GREEN: wrap overview", "ts": "2026-04-20T10:00:00+00:00"},
        {"iter": 2, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "s_003 satisfied via earlier impl", "ts": "2026-04-20T10:02:00+00:00"},
    ]
    goal_id, task_id = _bootstrap_task_with_plan(tmp_path, decisions=decisions)
    payload = build_overview_payload(tmp_path, goal_id, task_id=task_id)
    shipped = {s["id"]: s.get("shipped", False) for s in payload["step_shipping"]}
    assert shipped.get("s_001") is True, f"s_001 should be shipped: {shipped}"
    assert shipped.get("s_003") is True, f"s_003 should be shipped (via regex): {shipped}"
    assert shipped.get("s_002") is False, (
        f"s_002 must NOT be shipped (no tdd_green for it): {shipped}"
    )


def test_risk_delta_does_not_blanket_resolve_on_clean(tmp_path: Path) -> None:
    """redteam FM#6 — parallel_review=CLEAN must NOT blanket-promote
    every planned risk to resolved. Only risks with corpus-keyword
    evidence (tdd_green/review/approval reasoning) belong in resolved;
    the rest stay in remaining even if CLEAN."""
    import json as _json

    from agentboard.analytics.overview_payload import build_overview_payload
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_fp")
    board.goals.append(Goal(id="g_fp", title="fp", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_fp"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# plan\n")

    plan_payload = {
        "atomic_steps": [{"id": "s_001", "behavior": "x"}],
        "known_failure_modes": [
            "CRITICAL: alpha_marker_corpus_has_this",
            "HIGH: beta_marker_corpus_lacks_this_entirely",
        ],
    }
    (goal_dir / "plan.json").write_text(_json.dumps(plan_payload))
    task_dir = goal_dir / "tasks" / "t_fp"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(_json.dumps({"id": "t_fp", "status": "pushed"}))
    (task_dir / "decisions.jsonl").write_text(
        _json.dumps({"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
                     "reasoning": "alpha_marker_corpus_has_this resolved during impl"}) + "\n"
        + _json.dumps({"iter": 1, "phase": "parallel_review", "verdict_source": "CLEAN",
                       "reasoning": "no issues"}) + "\n"
    )

    payload = build_overview_payload(tmp_path, "g_fp", task_id="t_fp")
    rd = payload["risk_delta"]
    resolved_texts = " ".join(str(r) for r in rd["resolved"])
    remaining_texts = " ".join(str(r) for r in rd["remaining"])
    assert "alpha_marker" in resolved_texts, (
        f"risk with corpus evidence must be resolved:\n  resolved={rd['resolved']}\n  remaining={rd['remaining']}"
    )
    assert "beta_marker" in remaining_texts, (
        f"risk without corpus evidence must stay remaining EVEN with "
        f"parallel_review=CLEAN:\n  resolved={rd['resolved']}\n  remaining={rd['remaining']}"
    )


def test_risk_delta_cross_ref_uses_evidence_corpus(tmp_path: Path) -> None:
    """s_006 (redteam FM#6 revised) — payload.risk_delta classifies risks
    by per-risk keyword evidence in (tdd_green | review | approval)
    reasoning corpus. parallel_review=CLEAN is informational (shown in
    Review tab) but does NOT blanket-promote risks without evidence —
    avoids false-resolved risks."""
    import json as _json

    from agentboard.analytics.overview_payload import build_overview_payload
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".devboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_r")
    board.goals.append(Goal(id="g_r", title="r", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".devboard" / "goals" / "g_r"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# plan\n")

    plan_payload = {
        "atomic_steps": [
            {"id": "s_001", "behavior": "first"},
        ],
        "known_failure_modes": [
            "CRITICAL: keyword_alpha_mentioned_in_corpus",
            "HIGH: keyword_zeta_never_mentioned",
        ],
    }
    (goal_dir / "plan.json").write_text(_json.dumps(plan_payload))
    task_dir = goal_dir / "tasks" / "t_r"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(_json.dumps({"id": "t_r", "status": "pushed"}))
    # tdd_green reasoning references keyword_alpha; parallel_review=CLEAN
    # should NOT promote keyword_zeta (never mentioned anywhere).
    (task_dir / "decisions.jsonl").write_text(
        _json.dumps({"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
                     "reasoning": "fixed keyword_alpha_mentioned_in_corpus path"}) + "\n"
        + _json.dumps({"iter": 1, "phase": "parallel_review", "verdict_source": "CLEAN",
                       "reasoning": "no issues"}) + "\n"
    )

    payload = build_overview_payload(tmp_path, "g_r", task_id="t_r")
    rd = payload["risk_delta"]
    resolved_txt = " ".join(str(r) for r in rd["resolved"])
    remaining_txt = " ".join(str(r) for r in rd["remaining"])
    assert "keyword_alpha" in resolved_txt, (
        f"alpha (with corpus evidence) must be resolved: {rd}"
    )
    assert "keyword_zeta" in remaining_txt, (
        f"zeta (no evidence) must stay remaining despite CLEAN: {rd}"
    )


def test_step_shipping_uses_index_fallback_when_reasoning_lacks_step_id(
    tmp_path: Path,
) -> None:
    """s_004 edge — reasoning without 's_NNN' must still ship via index
    heuristic (iter N → atomic_steps[N-1]). Real-world TDD runs often phrase
    reasoning as `overview TabPane 본문을 VerticalScroll로 래핑` without
    explicitly re-stating `s_001`."""
    from agentboard.analytics.overview_payload import build_overview_payload

    decisions = [
        {"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "overview TabPane wrapped in VerticalScroll — no step id mentioned",
         "ts": "2026-04-20T10:00:00+00:00"},
        {"iter": 2, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "plan/dev/result/review tabs wrapped — also no step id",
         "ts": "2026-04-20T10:01:00+00:00"},
    ]
    goal_id, task_id = _bootstrap_task_with_plan(tmp_path, decisions=decisions)
    payload = build_overview_payload(tmp_path, goal_id, task_id=task_id)
    shipped = {s["id"]: s.get("shipped", False) for s in payload["step_shipping"]}
    assert shipped.get("s_001") is True, (
        f"s_001 must ship via index fallback (iter 1 → atomic_steps[0]): {shipped}"
    )
    assert shipped.get("s_002") is True, (
        f"s_002 must ship via index fallback (iter 2 → atomic_steps[1]): {shipped}"
    )


def test_iterations_include_step_cross_ref_fields(tmp_path: Path) -> None:
    """s_003 — iterations[i] must include behavior/test_file/test_name/impl_file
    copied from the matched atomic_step."""
    from agentboard.analytics.overview_payload import build_overview_payload

    goal_id, task_id = _bootstrap_task_with_plan(tmp_path)
    payload = build_overview_payload(tmp_path, goal_id, task_id=task_id)
    iters = payload["iterations"]
    assert iters, "no iterations extracted"
    first = iters[0]
    assert first.get("behavior") == "overview tab wraps VerticalScroll", (
        f"behavior missing or wrong: {first.get('behavior')!r}"
    )
    assert first.get("test_file") == "tests/test_tui_center_scroll.py", (
        f"test_file missing or wrong: {first.get('test_file')!r}"
    )
    assert first.get("test_name") == "test_overview_tab_wraps_static_in_vertical_scroll"
    assert first.get("impl_file") == "src/agentboard/tui/phase_flow.py"


def test_iterations_include_step_id_with_regex_priority(tmp_path: Path) -> None:
    """s_002 — reasoning containing 's_003' must yield step_id='s_003' even if
    the iter index would suggest a different step. Tests regex-first priority."""
    from agentboard.analytics.overview_payload import build_overview_payload

    # Put iter 1 with reasoning that says 's_003' — index heuristic would pick
    # s_001 (atomic_steps[0]), but regex must win.
    decisions = [
        {"iter": 1, "phase": "tdd_green", "verdict_source": "GREEN_CONFIRMED",
         "reasoning": "s_003 critical-path satisfied by earlier work",
         "ts": "2026-04-20T10:00:00+00:00"},
    ]
    goal_id, task_id = _bootstrap_task_with_plan(tmp_path, decisions=decisions)
    payload = build_overview_payload(tmp_path, goal_id, task_id=task_id)
    iters = payload["iterations"]
    assert iters, "no iterations extracted"
    assert iters[0].get("step_id") == "s_003", (
        f"regex must take priority over index heuristic: "
        f"iter 1 reasoning says s_003 but got step_id={iters[0].get('step_id')!r}"
    )
