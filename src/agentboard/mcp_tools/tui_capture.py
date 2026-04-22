"""Pilot-based TUI frame capture (text + SVG).

Companion to `tui_smoke.py`. Roles stay distinct:
  * tui_smoke — crash gate (does `agentboard board` mount in a real pty?)
  * tui_capture — frame extraction (Pilot in-process, text + SVG export)

Used by the `agentboard_tui_capture_snapshot` MCP tool and the
`agentboard-ui-preview` skill at Layer 1 (text) and Layer 2 (SVG).
"""

from __future__ import annotations

import asyncio
import html
import re
import threading
import time
import traceback as tb_module
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


_ANSI_SGR = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_TEXT_TAG_SUFFIX = "}text"  # namespace-agnostic local-name match


def _strip_ansi(text: str) -> str:
    return _ANSI_SGR.sub("", text)


_RESERVED_SAVE_PREFIXES: frozenset[str] = frozenset(
    p.casefold()
    for p in {
        # Devboard + VCS + project metadata
        ".devboard",
        ".git",
        ".github",
        ".mcp.json",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        ".env",
        # Python + tooling caches — clobbering these bricks dev env
        ".venv",
        "venv",
        ".vscode",
        ".idea",
        "__pycache__",
    }
)


def _resolve_save_path(root: Path, save_to: object) -> Path:
    """Resolve save_to against project_root with defense-in-depth rules.

    Rejects:
    - Non-string / empty save_to (MCP JSON may pass null, lists, etc.)
    - Absolute paths outside project_root, and `../` traversal
    - In-root reserved prefixes (.devboard/, .git/, .mcp.json, ...)
    - Target equal to project_root, or an existing directory

    This is the only write path the MCP tool exposes — without
    containment, a prompt-injected skill body or malicious MCP client
    could write anywhere the process has access, and overwriting
    `.devboard/state.json` alone would brick the board.
    """
    if not isinstance(save_to, str) or not save_to:
        raise ValueError(
            f"save_to must be a non-empty string (got {type(save_to).__name__})"
        )
    root_resolved = root.resolve()
    raw = Path(save_to)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve()
    try:
        rel = resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"save_to must stay under project_root (got {save_to!r})"
        ) from exc
    if resolved == root_resolved:
        raise ValueError("save_to must not equal project_root itself")
    if resolved.is_dir():
        raise ValueError(f"save_to points at an existing directory: {resolved!s}")
    head = rel.parts[0].casefold() if rel.parts else ""
    if head in _RESERVED_SAVE_PREFIXES:
        raise ValueError(
            f"save_to {save_to!r} hits a reserved in-root path "
            f"(prefix {rel.parts[0]!r}); move snapshots under e.g. "
            f"'tui_snapshots/'. Case-insensitive match — "
            f"macOS APFS collapses case so e.g. '.DEVBOARD' clobbers "
            f"'.devboard'."
        )
    return resolved


def _text_from_svg(svg: str) -> str:
    """Extract concatenated <text> contents from a Textual SVG screenshot.

    Walks the SVG tree, pulls `text` elements' descendant text (including
    tspan/title children), and unescapes HTML entities. Regex-based
    extraction silently loses `<text><tspan>X</tspan></text>` which
    Textual may emit for multi-style runs; the ET walk handles it.
    """
    if not svg:
        return ""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for el in root.iter():
        tag = el.tag
        if isinstance(tag, str) and (tag.endswith(_TEXT_TAG_SUFFIX) or tag == "text"):
            raw = "".join(el.itertext())
            decoded = html.unescape(raw)
            if decoded.strip():
                parts.append(decoded)
    return "\n".join(parts)


def _extract_text(app: Any) -> str:
    """Pull a plain-text frame out of a mounted Textual App.

    Uses `app.export_screenshot(simplify=False)` which embeds rendered
    text in <text> SVG nodes. The `render_lines` path returns a blank
    background for many apps in Pilot, so SVG→text is the reliable
    fallback that preserves the compositor's visible content.
    """
    try:
        svg = app.export_screenshot(simplify=False)
    except Exception:  # noqa: BLE001 — older / newer textual
        return ""
    return _text_from_svg(svg)


async def _capture_async(
    project_root: Path,
    keys: list[str],
    include_svg: bool,
    fixture_goal_id: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    from agentboard.tui.app import AgentBoardApp

    app = AgentBoardApp(store_root=project_root)
    if fixture_goal_id:
        known_ids = {g.get("id") for g in app.session.all_goals()}
        if fixture_goal_id not in known_ids:
            raise ValueError(
                f"fixture_goal_id {fixture_goal_id!r} not found in board "
                f"(known: {sorted(x for x in known_ids if x)})"
            )
    text = ""
    svg: str | None = None
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        if fixture_goal_id:
            app.session.set_active_goal(fixture_goal_id)
            app.refresh_for_active_goal()
            await pilot.pause()
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        text = _extract_text(app)
        if include_svg:
            try:
                svg = app.export_screenshot(simplify=False)
            except Exception:  # noqa: BLE001 — feature is opt-in
                svg = None
    return {"text": text, "svg": svg}


def run(
    project_root: str | Path,
    scene_id: str = "default",
    keys: list[str] | None = None,
    save_to: str | None = None,
    include_svg: bool = False,
    fixture_goal_id: str | None = None,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Spawn AgentBoardApp via Textual Pilot, press keys, capture frame.

    Returns: {text, svg, saved_txt, saved_svg, crashed, traceback,
              duration_s, scene_id}
    """
    root = Path(project_root)
    keys = keys or []
    started = time.time()

    # Fail-fast validation BEFORE spawning the Pilot worker — a bad
    # save_to or fixture_goal_id should not cost a full AgentBoardApp
    # mount + render cycle.
    if save_to is not None:
        try:
            _resolve_save_path(root, save_to)
        except ValueError as exc:
            return {
                "scene_id": scene_id,
                "text": "",
                "svg": None,
                "saved_txt": None,
                "saved_svg": None,
                "crashed": True,
                "traceback": f"save_to rejected: {exc}",
                "duration_s": round(time.time() - started, 3),
            }
    if fixture_goal_id is not None and not isinstance(fixture_goal_id, str):
        return {
            "scene_id": scene_id,
            "text": "",
            "svg": None,
            "saved_txt": None,
            "saved_svg": None,
            "crashed": True,
            "traceback": (
                f"fixture_goal_id must be a string (got "
                f"{type(fixture_goal_id).__name__})"
            ),
            "duration_s": round(time.time() - started, 3),
        }

    captured: dict[str, Any] = {}

    def _worker() -> None:
        # Run the capture in its own event loop so we can be invoked from
        # both sync code (tests) and an already-running MCP event loop.
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            captured.update(
                loop.run_until_complete(
                    _capture_async(
                        project_root=root,
                        keys=list(keys),
                        include_svg=include_svg,
                        fixture_goal_id=fixture_goal_id,
                        timeout_s=timeout_s,
                    )
                )
            )
        except Exception:  # noqa: BLE001 — capture any mount/render failure
            captured["_error"] = tb_module.format_exc()
        finally:
            loop.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s + 5.0)

    if thread.is_alive() or "_error" in captured:
        text = ""
        svg = None
        crashed = True
        traceback_text = captured.get("_error") or "capture worker timed out"
    else:
        text = captured.get("text", "")
        svg = captured.get("svg")
        crashed = False
        traceback_text = None

    saved_txt: str | None = None
    saved_svg: str | None = None
    if save_to is not None and not crashed:
        try:
            save_path = _resolve_save_path(root, save_to)
        except ValueError as exc:
            # Containment violation — refuse to write, propagate as crash.
            return {
                "scene_id": scene_id,
                "text": text,
                "svg": svg,
                "saved_txt": None,
                "saved_svg": None,
                "crashed": True,
                "traceback": f"save_to rejected: {exc}",
                "duration_s": round(time.time() - started, 3),
            }
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(text, encoding="utf-8")
        saved_txt = str(save_path)
        if include_svg and svg:
            svg_path = save_path.with_suffix(".svg")
            svg_path.write_text(svg, encoding="utf-8")
            saved_svg = str(svg_path)

    return {
        "scene_id": scene_id,
        "text": text,
        "svg": svg,
        "saved_txt": saved_txt,
        "saved_svg": saved_svg,
        "crashed": crashed,
        "traceback": traceback_text,
        "duration_s": round(time.time() - started, 3),
    }
