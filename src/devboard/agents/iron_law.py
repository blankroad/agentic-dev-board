from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devboard.tools.base import ToolCall


TEST_DIR_MARKERS = ("test_", "tests/", "_test.py", "/test")

# Claude Code uses "Write"/"Edit"; legacy LangGraph agent used "fs_write"
_WRITE_TOOL_NAMES = {"Write", "Edit", "fs_write"}


@dataclass
class IronLawVerdict:
    violated: bool
    reason: str = ""
    impl_writes: list[str] = None
    test_writes: list[str] = None

    def __post_init__(self):
        if self.impl_writes is None:
            self.impl_writes = []
        if self.test_writes is None:
            self.test_writes = []


def _extract_path(tc: ToolCall) -> str:
    # "Write"/"Edit" use file_path; legacy "fs_write" used path
    return str(tc.tool_input.get("file_path") or tc.tool_input.get("path", ""))


def check_iron_law(tool_calls: list[ToolCall]) -> IronLawVerdict:
    """Detect TDD Iron Law violations in an executor's tool call history.

    Violation: write to non-test file WITHOUT a preceding write to a test file
    in the same execution. Handles Claude Code tool names (Write, Edit) and
    legacy fs_write.

    Allowed: writes to test files alone, or test writes followed by impl writes.
    """
    impl_writes: list[str] = []
    test_writes: list[str] = []
    test_seen_before_impl = False

    for tc in tool_calls:
        if tc.tool_name not in _WRITE_TOOL_NAMES:
            continue
        path = _extract_path(tc)
        if _is_test_path(path):
            test_writes.append(path)
            if not impl_writes:
                test_seen_before_impl = True
        else:
            impl_writes.append(path)

    if impl_writes and not test_writes:
        return IronLawVerdict(
            violated=True,
            reason=f"Production code written without any test: {impl_writes}",
            impl_writes=impl_writes, test_writes=test_writes,
        )

    if impl_writes and not test_seen_before_impl:
        return IronLawVerdict(
            violated=True,
            reason=f"Test file written AFTER production code (tests must come first): impl={impl_writes}, tests={test_writes}",
            impl_writes=impl_writes, test_writes=test_writes,
        )

    return IronLawVerdict(
        violated=False,
        impl_writes=impl_writes,
        test_writes=test_writes,
    )


def _is_test_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    return any(m in p for m in TEST_DIR_MARKERS) or p.endswith("_test.py")
