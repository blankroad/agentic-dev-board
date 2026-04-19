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
