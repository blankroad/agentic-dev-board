"""agentboard_tui_capture_snapshot MCP + tui_capture module tests.

Covers: Pilot-based frame capture (text + SVG), key-sequence execution,
save_to serialization, MCP dispatch wiring, skill chain integration grep,
and e2e against real AgentBoardApp.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest


# ────────────────────────── helpers ──────────────────────────


def _bootstrap_goal(tmp_path: Path, gid: str = "g1") -> None:
    """Minimum .agentboard/ state so AgentBoardApp can mount against tmp_path."""
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".agentboard").mkdir(exist_ok=True)
    store = FileStore(tmp_path)
    try:
        board = store.load_board()
    except Exception:
        board = BoardState()
    board.goals.append(Goal(id=gid, title=gid, status=GoalStatus.active))
    store.save_board(board)
    gdir = tmp_path / ".agentboard" / "goals" / gid
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "plan.md").write_text("# plan\n", encoding="utf-8")


# ────────────────────────── s_001 ──────────────────────────


def test_tui_capture_module_exposes_run() -> None:
    """s_001: agentboard.mcp_tools.tui_capture module is importable and
    exposes a `run` callable.
    """
    from agentboard.mcp_tools import tui_capture

    assert callable(getattr(tui_capture, "run", None)), (
        "tui_capture module must expose a callable `run`"
    )


def test_run_returns_text_for_bootstrapped_app(tmp_path: Path) -> None:
    """s_002: run() mounts AgentBoardApp via Pilot and returns a dict with
    non-empty `text` key.

    # guards: integration-wiring
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    result = run(project_root=tmp_path, scene_id="default")
    assert isinstance(result, dict), f"result must be dict, got {type(result)}"
    assert result.get("crashed") is False, (
        f"capture must not crash; traceback={result.get('traceback')}"
    )
    text = result.get("text", "")
    assert isinstance(text, str) and len(text) > 0, (
        f"result['text'] must be non-empty string; got {text!r}"
    )


def test_run_presses_keys_in_order(tmp_path: Path) -> None:
    """s_003: run(keys=['2']) switches PhaseFlowView tabs via the App-
    level binding installed in the prior wedge, proving pilot.press fires.
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    before = run(project_root=tmp_path, scene_id="before", keys=[])
    after = run(project_root=tmp_path, scene_id="after", keys=["2"])
    # Pressing "2" activates the Dev tab (id="dev"); its body is the
    # Static#dev-body whose content differs from Plan tab. We assert the
    # captured text diff reflects the switch by looking for a Dev-only
    # tab-bar marker. If press didn't fire, the two frames would match.
    assert before["text"] != after["text"], (
        "captured text before/after press('2') must differ — "
        "otherwise keys are not being delivered to the app"
    )


def test_run_save_to_writes_file(tmp_path: Path) -> None:
    """s_004: run(save_to='snapshots/a.txt') writes the captured text to
    that path rooted at project_root.
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    result = run(
        project_root=tmp_path,
        scene_id="with_save",
        save_to="snapshots/plan.txt",
    )
    saved = result.get("saved_txt")
    assert saved, f"saved_txt must be set; got {saved!r}"
    saved_path = Path(saved)
    assert saved_path.exists(), f"save file must exist at {saved_path!r}"
    assert saved_path.read_text(encoding="utf-8") == result["text"]


def test_run_include_svg_populates_svg_field(tmp_path: Path) -> None:
    """s_005: run(include_svg=True) returns svg field containing '<svg'
    via textual's native App.export_screenshot. Also writes a sibling
    .svg file when save_to is provided.
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    result = run(
        project_root=tmp_path,
        scene_id="svg_scene",
        include_svg=True,
        save_to="snapshots/svg_scene.txt",
    )
    svg = result.get("svg")
    assert isinstance(svg, str) and "<svg" in svg, (
        f"result['svg'] must contain '<svg' tag; got len={len(svg or '')}"
    )
    saved_svg = result.get("saved_svg")
    assert saved_svg and Path(saved_svg).exists(), (
        f"saved_svg path must exist; got {saved_svg!r}"
    )


def test_mcp_list_tools_includes_capture_snapshot() -> None:
    """s_006: list_tools() returns an entry named agentboard_tui_capture_snapshot."""
    from agentboard import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = [t.name for t in tools]
    assert "agentboard_tui_capture_snapshot" in names, (
        f"MCP list_tools missing agentboard_tui_capture_snapshot; got {names}"
    )


def test_mcp_call_tool_dispatches_capture_snapshot(tmp_path: Path) -> None:
    """s_007: call_tool('agentboard_tui_capture_snapshot', ...) routes to
    tui_capture.run and returns its JSON-serializable dict.
    """
    from agentboard import mcp_server

    _bootstrap_goal(tmp_path)
    result = asyncio.run(
        mcp_server.call_tool(
            "agentboard_tui_capture_snapshot",
            {"project_root": str(tmp_path), "scene_id": "via_mcp"},
        )
    )
    # MCP tool responses are TextContent; parse payload JSON.
    assert result and hasattr(result[0], "text"), f"unexpected MCP result: {result!r}"
    payload = json.loads(result[0].text)
    assert payload.get("scene_id") == "via_mcp"
    assert payload.get("crashed") is False
    assert isinstance(payload.get("text"), str) and payload["text"]


# ────────────────────────── skill file tests ──────────────────────────


_REPO_ROOT = Path(__file__).resolve().parents[1]
_UI_PREVIEW_SKILL = _REPO_ROOT / "skills" / "agentboard-ui-preview" / "SKILL.md"


def _parse_frontmatter(md_path: Path) -> dict:
    import yaml

    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{md_path} missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"{md_path} frontmatter not closed")
    return yaml.safe_load(text[4:end])


def test_ui_preview_skill_has_valid_frontmatter() -> None:
    """s_008: agentboard-ui-preview SKILL.md exists with valid YAML
    frontmatter including name, description, when_to_use.
    """
    fm = _parse_frontmatter(_UI_PREVIEW_SKILL)
    assert fm.get("name") == "agentboard-ui-preview"
    assert fm.get("description"), "description required"
    assert fm.get("when_to_use"), "when_to_use required"


def test_ui_preview_skill_documents_four_layers() -> None:
    """s_009: SKILL.md contains all four Layer 0/1/2/3 section headings."""
    body = _UI_PREVIEW_SKILL.read_text(encoding="utf-8")
    for heading in ("Layer 0", "Layer 1", "Layer 2", "Layer 3"):
        assert heading in body, f"SKILL.md missing heading '{heading}'"


def test_ui_preview_skill_includes_scenes_schema() -> None:
    """s_010: SKILL.md includes scenes.yaml schema inline (scene_id + keys
    + description fields).
    """
    body = _UI_PREVIEW_SKILL.read_text(encoding="utf-8")
    assert "scenes.yaml" in body, "schema title scenes.yaml missing"
    for field in ("scene_id", "keys", "description"):
        assert field in body, f"scenes.yaml schema missing field '{field}'"


def test_architecture_skill_chains_ui_preview() -> None:
    """s_011 (T5 rename): agentboard-architecture SKILL.md mentions invoking
    agentboard-ui-preview when ui_surface is True. Replaces the deleted
    agentboard-gauntlet test — the UI hook moved to the D1 architecture
    phase during D3 cutover.
    """
    body = (_REPO_ROOT / "skills" / "agentboard-architecture" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "agentboard-ui-preview" in body, (
        "architecture SKILL.md must reference agentboard-ui-preview"
    )
    assert "ui_surface" in body


def test_execute_skill_chains_ui_preview() -> None:
    """s_012 (T5 rename): agentboard-execute SKILL.md invokes
    agentboard-ui-preview after first widget GREEN when ui_surface is
    True. Replaces the deleted agentboard-tdd test — execute is the D1
    chain's TDD loop.
    """
    body = (_REPO_ROOT / "skills" / "agentboard-execute" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "agentboard-ui-preview" in body, (
        "execute SKILL.md must reference agentboard-ui-preview"
    )
    assert "ui_surface" in body


def test_approval_skill_chains_ui_preview_svg() -> None:
    """s_013: agentboard-approval SKILL.md captures SVG via
    agentboard-ui-preview before push when ui_surface is True.
    """
    body = (_REPO_ROOT / "skills" / "agentboard-approval" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "agentboard-ui-preview" in body, (
        "approval SKILL.md must reference agentboard-ui-preview"
    )
    assert "ui_surface" in body
    assert "include_svg" in body or "Layer 2" in body, (
        "approval must invoke SVG capture (Layer 2)"
    )


_USER_SKILLS = Path.home() / ".claude" / "skills"


@pytest.mark.skipif(
    os.environ.get("RUN_INSTALL_MIRROR_TESTS") != "1",
    reason=(
        "Mirror integrity depends on `agentboard install` having run against "
        "the caller's ~/.claude/skills. Gated by RUN_INSTALL_MIRROR_TESTS=1 "
        "so CI and fresh clones don't fail before the install step."
    ),
)
def test_user_level_skill_mirrors_match_repo() -> None:
    """s_014: ~/.claude/skills/ mirrors are byte-identical to repo
    skills/ for all files touched this goal (ui-preview + gauntlet + tdd +
    approval).
    """
    for rel in (
        "agentboard-ui-preview/SKILL.md",
        "agentboard-gauntlet/SKILL.md",
        "agentboard-tdd/SKILL.md",
        "agentboard-approval/SKILL.md",
    ):
        repo = _REPO_ROOT / "skills" / rel
        user = _USER_SKILLS / rel
        assert repo.exists(), f"repo skill missing: {repo}"
        if not user.exists():
            pytest.fail(f"user-level mirror missing: {user}")
        a = hashlib.md5(repo.read_bytes()).hexdigest()
        b = hashlib.md5(user.read_bytes()).hexdigest()
        assert a == b, f"mirror drift for {rel}: repo={a} user={b}"


def test_fixture_goal_id_unknown_crashes_not_silently_blank(tmp_path: Path) -> None:
    """s_018 HIGH: a bogus fixture_goal_id must produce crashed=True
    (not a silently-default render that masquerades as the real goal).

    # guards: fixture-goal-validation
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path, gid="g_real")
    result = run(
        project_root=tmp_path,
        scene_id="bogus_fixture",
        fixture_goal_id="g_does_not_exist_9999",
    )
    assert result["crashed"] is True, (
        f"unknown fixture_goal_id must crash; got crashed=False text={result.get('text', '')[:120]!r}"
    )
    tb = result.get("traceback") or ""
    assert "fixture_goal_id" in tb, (
        f"traceback must mention fixture_goal_id; got {tb!r}"
    )


def test_text_from_svg_handles_tspan_children_and_entities() -> None:
    """s_017 HIGH: SVG <text> nodes may contain nested children (tspan,
    title) and HTML entities. _text_from_svg must extract readable text
    regardless, not silently drop them.

    # guards: svg-text-fragility
    """
    from agentboard.mcp_tools.tui_capture import _text_from_svg

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<text x="0" y="0"><tspan>Plan</tspan></text>'
        '<text x="0" y="10"><title>hover</title>Dev</text>'
        '<text x="0" y="20">A &amp; B</text>'
        "</svg>"
    )
    out = _text_from_svg(svg)
    for token in ("Plan", "Dev", "A & B"):
        assert token in out, (
            f"_text_from_svg dropped token {token!r} from tspan/entity SVG; got: {out!r}"
        )


@pytest.mark.parametrize(
    "reserved",
    [".DEVBOARD/state.json", ".Devboard/state.json", ".GIT/config", "Pyproject.toml", ".Env"],
)
def test_save_to_rejects_reserved_case_variants(tmp_path: Path, reserved: str) -> None:
    """s_025 CRITICAL: case-variant reserved paths must be refused even
    when the frozenset is lowercase — macOS APFS collapses '.DEVBOARD'
    to '.agentboard' and clobbers board state.

    # guards: reserved-path-denylist, case-insensitive-fs
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    state_json = tmp_path / ".agentboard" / "state.json"
    before = state_json.read_bytes() if state_json.exists() else b""
    result = run(
        project_root=tmp_path,
        scene_id="case_variant",
        save_to=reserved,
    )
    assert result["crashed"] is True, (
        f"case-variant reserved path {reserved!r} must crash; got crashed=False"
    )
    # If state.json exists in the bootstrap, it must not have been touched.
    if before:
        assert state_json.read_bytes() == before, (
            f"state.json was mutated via case-variant path {reserved!r}"
        )


def test_save_to_rejects_venv_subtree(tmp_path: Path) -> None:
    """s_026 HIGH: .venv must be in the reserved-prefix denylist —
    overwriting pyvenv.cfg or site-packages bricks the dev environment.
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    result = run(
        project_root=tmp_path,
        scene_id="venv_attack",
        save_to=".venv/pyvenv.cfg",
    )
    assert result["crashed"] is True, (
        "save_to under .venv must crash; got crashed=False"
    )


def test_fixture_goal_id_dict_type_returns_structured_crash(tmp_path: Path) -> None:
    """s_027 MEDIUM: fixture_goal_id as dict (also possible via MCP JSON)
    must produce the same structured crash as list — not a raw TypeError.
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    result = run(
        project_root=tmp_path,
        scene_id="dict_fixture",
        fixture_goal_id={"id": "g1"},  # type: ignore[arg-type]
    )
    assert result["crashed"] is True
    tb = result.get("traceback") or ""
    assert "fixture_goal_id" in tb


def test_save_to_rejects_reserved_in_root_paths(tmp_path: Path) -> None:
    """s_021 CRITICAL: in-root reserved files (.agentboard/state.json,
    .mcp.json, .git/**) must NOT be overwritten via save_to even though
    they technically live under project_root.

    # guards: reserved-path-denylist
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    state_json = tmp_path / ".agentboard" / "state.json"
    before = state_json.read_bytes() if state_json.exists() else b""
    assert before, "precondition: state.json must exist after bootstrap"

    result = run(
        project_root=tmp_path,
        scene_id="reserved_clobber",
        save_to=".agentboard/state.json",
    )
    assert result["crashed"] is True, (
        "save_to hitting a reserved in-root path must crash; "
        f"got crashed=False saved_txt={result.get('saved_txt')!r}"
    )
    assert state_json.read_bytes() == before, (
        "state.json must NOT be overwritten by save_to"
    )


def test_save_to_empty_returns_crashed_not_raises(tmp_path: Path) -> None:
    """s_022 HIGH: save_to='' or any existing directory must return a
    structured crashed=True dict — NOT raise IsADirectoryError that
    escapes run()'s MCP return contract.

    # guards: structured-crash-contract
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    # Should not raise — should return a crashed dict.
    result = run(project_root=tmp_path, scene_id="empty_save", save_to="")
    assert isinstance(result, dict)
    assert result["crashed"] is True, (
        f"save_to='' must crash via return value; got crashed=False"
    )


def test_save_to_violation_skips_pilot_capture(tmp_path: Path) -> None:
    """s_023 MEDIUM: containment violation must be detected BEFORE the
    Pilot/AgentBoardApp thread spawns. Probe via timing — a rejected path
    should return in < 200ms (no mount), vs. a valid path ≈400ms.

    # guards: fail-fast-ordering
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    result = run(
        project_root=tmp_path,
        scene_id="fail_fast",
        save_to="../escape.txt",
    )
    assert result["crashed"] is True
    assert result["duration_s"] < 0.2, (
        f"rejection should skip Pilot mount — duration must be <200ms, got {result['duration_s']}s"
    )


def test_fixture_goal_id_non_string_returns_structured_crash(tmp_path: Path) -> None:
    """s_024 MEDIUM: fixture_goal_id passed as non-string (list/dict
    from malformed MCP JSON) must produce the same friendly crash as an
    unknown string — not a raw TypeError escaping the capture worker.

    # guards: fixture-type-guard
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    result = run(
        project_root=tmp_path,
        scene_id="bad_fixture_type",
        fixture_goal_id=["g1"],  # type: ignore[arg-type]
    )
    assert result["crashed"] is True
    tb = result.get("traceback") or ""
    assert "fixture_goal_id" in tb, (
        f"traceback must mention fixture_goal_id, not raw TypeError; got {tb!r}"
    )


def test_save_to_rejects_absolute_path_outside_project_root(tmp_path: Path) -> None:
    """s_016 CRITICAL: absolute save_to outside project_root must be
    refused — otherwise any MCP caller can write arbitrary files.

    # guards: path-traversal-containment
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    outside = tmp_path.parent / "REDTEAM_should_not_write.txt"
    result = run(
        project_root=tmp_path,
        scene_id="abs_escape",
        save_to=str(outside),
    )
    assert result["crashed"] is True, (
        "absolute save_to outside project_root must crash (got crashed=False)"
    )
    assert not outside.exists(), (
        f"file must NOT be created outside project_root: {outside}"
    )


def test_save_to_rejects_relative_traversal_outside_project_root(tmp_path: Path) -> None:
    """s_016 CRITICAL: relative save_to with ../ escaping project_root
    must also be refused.

    # guards: path-traversal-containment
    """
    from agentboard.mcp_tools.tui_capture import run

    _bootstrap_goal(tmp_path)
    # After bootstrap, tmp_path itself is the project root. Traversing
    # upward must not escape it.
    target_outside = tmp_path.parent / "REDTEAM_traversal_guard.txt"
    result = run(
        project_root=tmp_path,
        scene_id="rel_escape",
        save_to="../REDTEAM_traversal_guard.txt",
    )
    assert result["crashed"] is True, (
        "../-traversal save_to must crash (got crashed=False)"
    )
    assert not target_outside.exists(), (
        f"file must NOT be created via traversal: {target_outside}"
    )


def test_e2e_capture_snapshot_reveals_plan_tab(tmp_path: Path) -> None:
    """s_015: end-to-end — agentboard_tui_capture_snapshot against a real
    AgentBoardApp with a bootstrapped goal returns text containing the
    'Plan' tab label from PhaseFlowView (proves the full chain from MCP
    → dispatch → tui_capture.run → Pilot → SVG→text extraction works).
    """
    from agentboard import mcp_server

    _bootstrap_goal(tmp_path)
    result = asyncio.run(
        mcp_server.call_tool(
            "agentboard_tui_capture_snapshot",
            {
                "project_root": str(tmp_path),
                "scene_id": "e2e",
                "save_to": "tui_snapshots/e2e/plan_default.txt",
                "include_svg": True,
            },
        )
    )
    payload = json.loads(result[0].text)
    assert payload["crashed"] is False, f"e2e crashed: {payload.get('traceback')}"
    text = payload["text"]
    assert "Plan" in text, (
        f"captured frame must include 'Plan' tab label; got: {text[:300]!r}"
    )
    # Verify Layer 2 artifacts also written
    assert payload["saved_txt"] and Path(payload["saved_txt"]).exists()
    assert payload["saved_svg"] and Path(payload["saved_svg"]).exists()
