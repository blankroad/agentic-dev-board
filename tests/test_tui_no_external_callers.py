from __future__ import annotations

import subprocess
from pathlib import Path


def test_no_external_callers_of_tui_app_loop_callbacks() -> None:
    """Nothing outside src/agentboard/tui/ may call the orchestrator-loop
    callbacks on DevBoardApp (log_step, log_verdict, log_tool,
    notify_converged, set_gauntlet_step). These exist for a LEGACY
    orchestrator wire that we are removing; external references would break.

    The public entry point ``run_tui`` is exempt — cli.py uses it.
    """
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    pattern = r"\.(log_step|log_verdict|log_tool|notify_converged|set_gauntlet_step)\("
    result = subprocess.run(
        ["grep", "-rln", "--include=*.py", "-E", pattern, str(src)],
        capture_output=True,
        text=True,
        check=False,
    )
    matches = [ln for ln in result.stdout.splitlines() if ln.strip()]
    tui_pkg = str(src / "devboard" / "tui")
    external = [m for m in matches if not m.startswith(tui_pkg)]
    assert external == [], f"external callers of TUI loop callbacks found: {external}"
