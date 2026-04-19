from __future__ import annotations
from enum import Enum

class PlanSection(str, Enum):
    METADATA = "Metadata"
    OUTCOME = "Outcome"
    SCREENSHOTS = "Screenshots / Diagrams"
    LESSONS = "Lessons"
