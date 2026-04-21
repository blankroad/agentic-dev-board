"""Optional OTel emitter that forwards iter events to Langfuse (M2).

Design (autoplan HYBRID verdict): Langfuse covers ~35% of D''
(session/trace model + web viewer + public share links + cross-run
search). Instead of building those features, offer an OPTIONAL emitter
that users opt into via env var. When enabled, every
`agentboard_log_decision` dispatched with rid+gid emits one OTel-style
span that Langfuse ingests.

Invariants:
1. Default OFF. No import, no cost when `LANGFUSE_PUBLIC_KEY` env unset.
2. SDK absence is ignored. `pip install agentic-dev-board[langfuse]`
   required to make this do anything.
3. NEVER propagate exceptions. Telemetry is below-the-line — a Langfuse
   outage must not break MCP dispatch.
"""
from __future__ import annotations

import os
from typing import Any


_LANGFUSE_ENV_KEY = "LANGFUSE_PUBLIC_KEY"


def _is_enabled() -> bool:
    """Environment gate — no langfuse import happens before this returns True."""
    return bool(os.environ.get(_LANGFUSE_ENV_KEY))


def emit_iter(
    rid: str,
    iter_data: dict[str, Any],
    gid: str | None = None,
    tid: str | None = None,
) -> None:
    """Emit one OTel span to Langfuse for a pile iter write.

    Silent no-op when env unset, SDK missing, or any error occurs.
    """
    if not _is_enabled():
        return

    try:
        # Lazy-import so the optional dep cost is paid only when enabled
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except Exception:
        # SDK not installed — silent
        return

    try:
        client = Langfuse()  # reads LANGFUSE_* env vars directly
        phase = str(iter_data.get("phase", "unknown"))
        iter_n = iter_data.get("iter_n", 0)
        name = f"iter-{iter_n}-{phase}"
        metadata = {
            "rid": rid,
            "gid": gid,
            "tid": tid,
            "phase": phase,
            "iter_n": iter_n,
            "verdict_source": iter_data.get("verdict_source", ""),
            "gen_ai.system": "claude-code",
        }
        # Prefer v3 span API; fall back to trace if absent.
        if hasattr(client, "span"):
            span = client.span(
                name=name,
                input=iter_data.get("reasoning", ""),
                metadata=metadata,
            )
            try:
                if hasattr(span, "end"):
                    span.end()
            except Exception:
                pass
        elif hasattr(client, "trace"):
            client.trace(name=name, metadata=metadata)
        # Flush if possible so spans reach the remote before process exit.
        if hasattr(client, "flush"):
            try:
                client.flush()
            except Exception:
                pass
    except Exception:
        # Any SDK error is swallowed. Primary dispatch path stays green.
        return
