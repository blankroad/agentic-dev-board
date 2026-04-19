from __future__ import annotations
from pathlib import Path


def test_plan_section_enum_has_four_known_members() -> None:
    """# guards: edge-case-red-rule
    edge: empty — enum must be stable and enumerable without instantiation."""
    from devboard.docs.plan_sections import PlanSection
    assert {m.value for m in PlanSection} == {
        "Metadata", "Outcome", "Screenshots / Diagrams", "Lessons",
    }


def test_upsert_appends_when_section_missing(tmp_path: Path) -> None:
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section
    plan = tmp_path / "plan.md"
    plan.write_text("# Goal\n\n## Problem\n\nexisting body\n")
    upsert_plan_section(plan, PlanSection.OUTCOME, "status: pushed")
    text = plan.read_text()
    assert "## Problem" in text, "existing content must survive"
    assert "## Outcome" in text, "new section must appear"
    assert "status: pushed" in text
    assert text.index("## Problem") < text.index("## Outcome")


def test_upsert_replaces_when_section_exists(tmp_path: Path) -> None:
    """# guards: edge-case-red-rule
    edge: cached stale — second upsert must replace, not stack."""
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section
    plan = tmp_path / "plan.md"
    plan.write_text("# G\n\n## Problem\n\nx\n")
    upsert_plan_section(plan, PlanSection.OUTCOME, "first")
    upsert_plan_section(plan, PlanSection.OUTCOME, "second")
    text = plan.read_text()
    assert text.count("## Outcome") == 1, f"must not stack: {text!r}"
    assert "second" in text
    assert "first" not in text


def test_upsert_creates_file_when_missing(tmp_path: Path) -> None:
    """# guards: edge-case-red-rule
    edge: empty input — plan.md doesn't exist yet."""
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section
    plan = tmp_path / "plan.md"
    assert not plan.exists()
    upsert_plan_section(plan, PlanSection.METADATA, "goal_id: g_xxx")
    assert plan.exists()
    assert "## Metadata" in plan.read_text()
    assert "goal_id: g_xxx" in plan.read_text()


def test_upsert_on_empty_file_writes_single_block(tmp_path: Path) -> None:
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section
    plan = tmp_path / "plan.md"
    plan.write_text("")
    upsert_plan_section(plan, PlanSection.LESSONS, "learned X")
    text = plan.read_text()
    assert text.startswith("## Lessons"), f"no leading whitespace: {text!r}"
    assert "learned X" in text


def test_upsert_does_not_clobber_binary_plan(tmp_path: Path) -> None:
    """# guards: read-text-in-compose-must-catch-unicode
    edge: binary / non-UTF-8 file — must NOT overwrite a corrupted file
    with a fresh block (data loss risk). Should fall through quietly."""
    from devboard.docs.plan_sections import PlanSection, upsert_plan_section

    plan = tmp_path / "plan.md"
    bad = b"\xff\xfe\x00garbled"
    plan.write_bytes(bad)

    # Must not raise
    upsert_plan_section(plan, PlanSection.OUTCOME, "status: pushed")

    # Original bytes preserved — we refused to touch it
    assert plan.read_bytes() == bad
