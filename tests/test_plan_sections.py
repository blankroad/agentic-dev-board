from __future__ import annotations
from pathlib import Path
import pytest

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
