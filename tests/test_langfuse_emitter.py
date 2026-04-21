"""Langfuse OTel emitter tests (M2-langfuse l_001-l_005).

All tests inject fake langfuse modules via monkeypatch — no real network.
"""
from __future__ import annotations

import json
import sys
import types

import pytest


def test_langfuse_emitter_module_exists() -> None:
    """l_001: telemetry.langfuse_emitter module + emit_iter function."""
    from agentboard.telemetry.langfuse_emitter import emit_iter
    assert callable(emit_iter)


def test_emit_iter_no_op_when_env_unset(monkeypatch) -> None:
    """l_002: emit_iter returns None and does not import langfuse when env unset."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

    # Ensure langfuse NOT in sys.modules so import attempt would be observable
    import_count = 0
    orig_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def counted_import(name, *args, **kwargs):
        nonlocal import_count
        if name == "langfuse":
            import_count += 1
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", counted_import)

    from agentboard.telemetry.langfuse_emitter import emit_iter
    result = emit_iter(
        rid="run_x", iter_data={"phase": "tdd_green", "iter_n": 1}, gid="g", tid="t",
    )
    assert result is None
    assert import_count == 0, "langfuse import attempted when env unset"


def test_emit_iter_swallows_sdk_errors(monkeypatch) -> None:
    """l_003: emit_iter never propagates exceptions when SDK raises."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")

    # Inject fake langfuse module whose Langfuse() constructor raises
    fake_mod = types.ModuleType("langfuse")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("simulated init failure")

    fake_mod.Langfuse = FakeClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_mod)

    from agentboard.telemetry.langfuse_emitter import emit_iter
    # Must not raise
    result = emit_iter(
        rid="run_x", iter_data={"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t",
    )
    assert result is None


def test_emit_iter_calls_sdk_when_available(monkeypatch) -> None:
    """l_004: emit_iter invokes injected SDK when env set and no error."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")

    captured_spans: list[dict] = []

    class FakeSpan:
        def __init__(self, name, input=None, metadata=None):
            captured_spans.append({
                "name": name, "input": input, "metadata": metadata or {},
            })

        def end(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def span(self, name, input=None, metadata=None):
            return FakeSpan(name, input=input, metadata=metadata)

        # Compat: v2/v3 SDKs may offer trace() instead
        def trace(self, **kw):
            return FakeSpan(kw.get("name", "trace"))

        def flush(self):
            pass

    fake_mod = types.ModuleType("langfuse")
    fake_mod.Langfuse = FakeClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_mod)

    from agentboard.telemetry.langfuse_emitter import emit_iter
    emit_iter(
        rid="run_mcp", iter_data={
            "phase": "tdd_green", "iter_n": 7,
            "verdict_source": "GREEN_CONFIRMED",
            "reasoning": "test",
        },
        gid="g_x", tid="t_x",
    )
    assert len(captured_spans) == 1, f"expected 1 span, got {len(captured_spans)}"
    md = captured_spans[0]["metadata"]
    assert md.get("phase") == "tdd_green"
    assert md.get("iter_n") == 7
    assert md.get("rid") == "run_mcp"


async def test_log_decision_dispatch_calls_emit_iter(tmp_path, monkeypatch) -> None:
    """l_005: mcp_server devboard_log_decision dispatch invokes emit_iter
    after pile sibling write when rid+gid are passed.
    """
    calls: list[dict] = []

    def fake_emit(rid, iter_data, gid=None, tid=None):
        calls.append({
            "rid": rid, "iter_data": iter_data, "gid": gid, "tid": tid,
        })

    # Patch the emitter symbol as imported by mcp_server
    monkeypatch.setattr(
        "agentboard.telemetry.langfuse_emitter.emit_iter", fake_emit
    )

    from agentboard.mcp_server import call_tool

    gid = "g_emit"
    tid = "t_emit"
    task_dir = tmp_path / ".devboard" / "goals" / gid / "tasks" / tid
    task_dir.mkdir(parents=True)

    result = await call_tool(
        "agentboard_log_decision",
        {
            "project_root": str(tmp_path),
            "task_id": tid,
            "iter": 3,
            "phase": "tdd_green",
            "reasoning": "test",
            "verdict_source": "GREEN_CONFIRMED",
            "rid": "run_emit",
            "gid": gid,
        },
    )
    payload = json.loads(result[0].text)
    assert payload.get("status") == "logged"

    assert len(calls) == 1, f"emit_iter not invoked from dispatch; calls={calls}"
    call = calls[0]
    assert call["rid"] == "run_emit"
    assert call["iter_data"].get("phase") == "tdd_green"
    assert call["iter_data"].get("iter_n") == 3
    assert call["gid"] == gid
    assert call["tid"] == tid
