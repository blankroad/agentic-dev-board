from __future__ import annotations

import re
from pathlib import Path


def test_save_tui_capture_writes_file_with_iso_ts_stem(tmp_path: Path) -> None:
    from agentboard.mcp_tools.capture_store import save_tui_capture

    (tmp_path / ".devboard" / "goals" / "g_x").mkdir(parents=True)
    capture = {"mounted": True, "crashed": False, "captured_bytes": 42, "duration_s": 1.5}
    path = save_tui_capture(tmp_path, "g_x", capture)

    assert path.exists()
    assert path.parent.name == "captures"
    assert re.match(r"tui_\d{8}T\d{6}Z\.txt", path.name), f"bad stem: {path.name}"
    content = path.read_text()
    for k in capture:
        assert k in content


def test_save_tui_capture_creates_captures_dir(tmp_path: Path) -> None:
    """# guards: edge-case-red-rule
    edge: empty input — captures/ may not exist yet."""
    from agentboard.mcp_tools.capture_store import save_tui_capture

    (tmp_path / ".devboard" / "goals" / "g_y").mkdir(parents=True)
    assert not (tmp_path / ".devboard" / "goals" / "g_y" / "captures").exists()
    save_tui_capture(tmp_path, "g_y", {})
    assert (tmp_path / ".devboard" / "goals" / "g_y" / "captures").is_dir()
