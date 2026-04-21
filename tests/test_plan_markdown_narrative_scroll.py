"""Narrative audit PoC tests for goal g_20260419_231208_af78bb.

Approach B (golden sample + hardcoded render PoC): prove that the existing
`PlanMarkdown` widget renders a 5-section "Purpose -> Plan -> Process ->
Result -> Review" narrative when `plan_summary.md` holds the golden fixture
content, with zero production code change.

See `.devboard/goals/g_20260419_231208_af78bb/audit/` for the accompanying
hand-authored narrative, target-goal selection record, gap-mapping table,
and the follow-up automation spec.
"""

from __future__ import annotations

import re
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "narrative_golden.md"
REQUIRED_HEADERS: tuple[str, ...] = (
    "Purpose",
    "Plan",
    "Process",
    "Result",
    "Review",
)


def _read_fixture_from(path: Path) -> str:
    """Read a fixture file and normalize CRLF -> LF so header-anchored
    regexes and per-section length checks behave identically regardless
    of the contributor's git autocrlf / OS line-ending default."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _read_fixture() -> str:
    return _read_fixture_from(FIXTURE_PATH)


def test_read_fixture_of_crlf_file_returns_lf_only(tmp_path: Path) -> None:
    """# guards: crlf-line-ending-drift (redteam BROKEN finding #3)

    A contributor on Windows with `core.autocrlf=true` (or a missing
    `.gitattributes`) can commit the fixture with CRLF. The `^...$`
    anchors in the header regex still match via `\\s`, but any
    accidental `\\r` before `##` breaks the line-start anchor, and
    downstream consumers that count chars treat `\\r` as non-blank.
    Normalize CRLF -> LF at read time so all fixture-parsing tests
    are stable regardless of line-ending style.
    """
    crlf_path = tmp_path / "crlf.md"
    crlf_path.write_bytes(
        b"## Purpose\r\n\r\nbody\r\n## Plan\r\n\r\nmore\r\n"
    )
    text = _read_fixture_from(crlf_path)
    assert "\r" not in text, (
        f"CRLF not normalized; \\r count = {text.count(chr(13))}"
    )


def test_narrative_golden_fixture_has_five_h2_headers() -> None:
    """Structural contract: the golden fixture carries exactly the five
    narrative H2 headers (Purpose, Plan, Process, Result, Review) in
    that order."""
    text = _read_fixture()
    found = re.findall(r"^##\s+(\w+)\s*$", text, flags=re.MULTILINE)
    assert found == list(REQUIRED_HEADERS), (
        f"expected H2 headers {REQUIRED_HEADERS!r}, got {found!r}"
    )


async def test_plan_markdown_receives_five_section_narrative_as_markdown_source(
    tmp_path: Path,
) -> None:
    """Integration proof (Pilot-level): booting DevBoardApp with a
    plan_summary.md containing the 5-section fixture results in the
    PlanMarkdown widget's body holding a rich.Markdown whose source
    text carries all 5 headers + per-section anchors.

    Narrowed claim: this proves the fixture *reached* the widget as
    Markdown source (via FileStore read -> SessionContext resolve ->
    PlanMarkdown._load -> rich.Markdown construction). It does NOT
    prove that rich.Markdown produced visible rendered text — that
    proof is agentboard_tui_render_smoke's job, triggered at approval
    time by ui_surface=true (see redteam finding #2, iter=3 parallel_review).

    # guards: unit-tests-on-primitives-dont-prove-integration
    # guards: ui-requires-real-tty-smoke-not-just-pytest
    """
    from rich.markdown import Markdown

    from agentboard.tui.app import DevBoardApp

    # SessionContext.active_goal_id resolves by walking goals/*/plan.md
    # mtime — it ignores BoardState.active_goal_id. Creating just the
    # goal dir with plan_summary.md is sufficient; no save_board call.
    # (See redteam finding #4, iter=3 parallel_review.)
    (tmp_path / ".devboard").mkdir()
    goal_dir = tmp_path / ".devboard" / "goals" / "g_narrative"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan_summary.md").write_text(_read_fixture(), encoding="utf-8")
    # Intentionally no runs/ dir — DevBoardApp.on_mount's RunTailWorker
    # guard skips when .devboard/runs is absent, avoiding Pilot flakiness.

    # Unique per-section anchor strings — ensures every section body
    # round-tripped through PlanMarkdown._load(), not just the headers.
    section_anchors = {
        "Purpose": "cockpit existed but had no instruments",
        "Plan": "25 atomic TDD steps",
        "Process": "Round 4 (iter 11) returned SURVIVED",
        "Result": "commit `33543cd`",
        "Review": "unit-tests-on-primitives-dont-prove-integration",
    }

    app = DevBoardApp(store_root=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        body = app.query_one("#plan-body")
        content = body.content
        assert isinstance(content, Markdown), type(content).__name__
        source = content.markup
        assert "Plan not locked" not in source, (
            "PlanMarkdown fell back to 'Plan not locked' — plan_summary.md "
            "was not loaded from the tmp store"
        )
        missing_headers = [h for h in REQUIRED_HEADERS if f"## {h}" not in source]
        assert not missing_headers, (
            f"PlanMarkdown source missing narrative headers: {missing_headers!r}"
        )
        missing_anchors = {
            name: anchor
            for name, anchor in section_anchors.items()
            if anchor not in source
        }
        assert not missing_anchors, (
            f"PlanMarkdown source missing section anchors (integration broken): "
            f"{missing_anchors!r}"
        )


def test_narrative_golden_sections_have_min_length() -> None:
    """Content-density contract: every section body carries >=100
    non-blank characters so the gap-mapping audit reasons about realistic
    narrative density, not placeholder stubs."""
    text = _read_fixture()
    parts = re.split(r"^##\s+(\w+)\s*\n", text, flags=re.MULTILINE)
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        name = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections[name] = body
    for name in REQUIRED_HEADERS:
        assert name in sections, f"missing section '{name}'"
        non_blank = "".join(ch for ch in sections[name] if not ch.isspace())
        assert len(non_blank) >= 100, (
            f"section '{name}' has {len(non_blank)} non-blank chars, need >=100"
        )
