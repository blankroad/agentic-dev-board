from __future__ import annotations
from enum import Enum
from pathlib import Path

from agentboard.storage.file_store import atomic_write, file_lock


class PlanSection(str, Enum):
    METADATA = "Metadata"
    OUTCOME = "Outcome"
    SCREENSHOTS = "Screenshots / Diagrams"
    LESSONS = "Lessons"


def upsert_plan_section(plan_path: Path, section: PlanSection, content: str) -> None:
    """Replace or append a `## <section>` block in plan.md. Idempotent."""
    heading = f"## {section.value}"
    block = f"{heading}\n\n{content.rstrip()}\n"
    with file_lock(plan_path):
        if plan_path.exists():
            try:
                original = plan_path.read_text()
            except (OSError, UnicodeDecodeError):
                # Corrupted / binary plan.md — refuse to clobber. Skill caller
                # sees a no-op; user can fix the file and re-run.
                return
        else:
            original = ""
        if heading in _section_headings(original):
            new_text = _replace_section(original, heading, block)
        else:
            sep = "" if not original else ("" if original.endswith("\n\n") else ("\n" if original.endswith("\n") else "\n\n"))
            new_text = original + sep + block
        atomic_write(plan_path, new_text)


def _section_headings(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("## ")]


def _replace_section(original: str, heading: str, new_block: str) -> str:
    lines = original.splitlines(keepends=True)
    try:
        start = next(i for i, ln in enumerate(lines) if ln.rstrip("\n") == heading)
    except StopIteration:
        return original + new_block
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "".join(lines[:start]) + new_block + "".join(lines[end:])
