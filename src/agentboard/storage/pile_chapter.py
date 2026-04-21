"""ChapterWriter — labor chapter regenerator (M1a-data).

Deterministic template: joins per-iter markdown lines from phase renderers,
then applies greedy-from-oldest truncation until under budget while
pinning verdict iters (redteam/approval).

M1a-data scope covers the "labor" chapter only. Other chapters
(contract / verdict / delta) are M1a-plumbing or M2.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentboard.storage.file_store import atomic_write
from agentboard.tui.phases import FallbackRenderer
from agentboard.tui.phases.approval import md_from_dict as _approval_md
from agentboard.tui.phases.redteam import md_from_dict as _redteam_md
from agentboard.tui.phases.tdd import md_from_dict as _tdd_md

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore


CHAPTER_BUDGET_TOK_DEFAULT = 3000
CHAR_PER_TOK = 3.5

_VERDICT_PHASES = frozenset({"redteam", "approval"})


def _render_iter(d: dict) -> str:
    """Dispatch a single iter dict to the right phase's md_from_dict."""
    phase = str(d.get("phase", ""))
    if phase.startswith("tdd"):
        return _tdd_md(d)
    if phase == "redteam":
        return _redteam_md(d)
    if phase == "approval":
        return _approval_md(d)
    return FallbackRenderer().render_markdown(d)


def _is_verdict(d: dict) -> bool:
    return str(d.get("phase", "")) in _VERDICT_PHASES


class ChapterWriter:
    """Writes chapters/labor.md from iter artifacts."""

    def __init__(self, store: "FileStore", budget_tok: int = CHAPTER_BUDGET_TOK_DEFAULT) -> None:
        self._store = store
        self._budget_chars = int(budget_tok * CHAR_PER_TOK)

    def _pile_dir(self, rid: str) -> Path:
        return self._store._run_pile_dir(rid)  # type: ignore[attr-defined]

    def _iter_dicts(self, rid: str) -> list[dict]:
        iters_dir = self._pile_dir(rid) / "iters"
        if not iters_dir.exists():
            return []
        out = []
        for p in sorted(iters_dir.glob("iter-*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
        return out

    def regen_labor(self, rid: str) -> Path:
        """Regenerate chapters/labor.md for a run. Atomic."""
        iters = self._iter_dicts(rid)
        lines = [_render_iter(d) for d in iters]

        # Initial assemble — header + all iter lines
        header = [
            "# Chapter — Labor",
            "",
            f"_{len(iters)} iterations · run `{rid}`_",
            "",
        ]
        body_lines = list(lines)
        content = "\n".join(header + body_lines)

        # If over budget, greedy-from-oldest collapse non-verdict iters.
        # Keep collapsing until under budget OR only verdict iters remain.
        if len(content) > self._budget_chars:
            non_verdict_idx = [
                i for i, d in enumerate(iters) if not _is_verdict(d)
            ]
            collapsed: set[int] = set()

            def _render_with_collapse(collapsed_set: set[int]) -> str:
                filtered: list[str] = []
                placed_marker = False
                for j, ln in enumerate(body_lines):
                    if j in collapsed_set:
                        if not placed_marker:
                            filtered.append(
                                f"- iters 1-{len(collapsed_set)}: aggregate "
                                f"({len(collapsed_set)} non-verdict iters collapsed)"
                            )
                            placed_marker = True
                    else:
                        filtered.append(ln)
                return "\n".join(header + filtered)

            for idx in non_verdict_idx:
                if len(_render_with_collapse(collapsed)) <= self._budget_chars:
                    break
                collapsed.add(idx)

            content = _render_with_collapse(collapsed)
            # Rewrite body_lines to match collapsed view (for later tight-budget step)
            tmp: list[str] = []
            placed = False
            for j, ln in enumerate(body_lines):
                if j in collapsed:
                    if not placed:
                        tmp.append(
                            f"- iters 1-{len(collapsed)}: aggregate "
                            f"({len(collapsed)} non-verdict iters collapsed)"
                        )
                        placed = True
                else:
                    tmp.append(ln)
            body_lines = tmp

        # If still over budget (verdict-only case), truncate verdict
        # narratives by keeping title/status only. We approximate by
        # collapsing any multi-line iter to its first line.
        if len(content) > self._budget_chars:
            shortened = []
            for ln in body_lines:
                shortened.append(ln.split("\n", 1)[0])
            body_lines = shortened
            content = "\n".join(header + body_lines)

        # Final fallback (redteam F3): if truncation insufficient — the
        # all-verdict tight-budget case — drop oldest iters entirely,
        # keeping the most recent ones, with an aggregate marker. The
        # agent still gets recent state; older verdict details live in
        # iters/iter-NNN.json and can be fetched individually.
        if len(content) > self._budget_chars:
            kept_lines = list(body_lines)
            dropped_count = 0
            while len(kept_lines) > 1 and len("\n".join(
                header + [f"- (dropped {dropped_count} oldest verdict iters — see iters/iter-*.json)"] + kept_lines[dropped_count:]
            )) > self._budget_chars:
                dropped_count += 1
            marker = [
                f"- (dropped {dropped_count} oldest verdict iters — see iters/iter-*.json)"
            ] if dropped_count > 0 else []
            body_lines = marker + kept_lines[dropped_count:]
            content = "\n".join(header + body_lines)

        chapter_path = self._pile_dir(rid) / "chapters" / "labor.md"
        atomic_write(chapter_path, content)
        return chapter_path
