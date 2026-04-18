from __future__ import annotations

from pathlib import Path


def test_no_orchestrator_interrupt_import_in_new_app() -> None:
    """src/devboard/tui/app.py (v2.0) must not import the LEGACY
    orchestrator.interrupt module. The legacy path lives in app_legacy.py
    only."""
    app_py = Path(__file__).resolve().parent.parent / "src" / "devboard" / "tui" / "app.py"
    source = app_py.read_text()
    assert "devboard.orchestrator.interrupt" not in source, (
        "new app.py still references LEGACY orchestrator.interrupt"
    )
    assert "get_hint_queue" not in source, "new app.py still calls get_hint_queue"
