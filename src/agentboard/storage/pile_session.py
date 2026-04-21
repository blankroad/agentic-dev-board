"""SessionWriter — index-form session.md for a run.

Budget: ≤500 tok (≈1750 chars). Structure:
- Header (goal title, truncated to 60 chars)
- Per-chapter 1-line teasers (agent discovery pattern — DX fix per autoplan)
- 3-line As-Is → To-Be delta placeholder (filled by M2 LLM synth overlay)
- Status line (iter N/M · current phase · last verdict)

The teasers are the key agent discovery affordance: an LLM calling
agentboard_get_session(rid) reads 500 tok and immediately knows which
chapter to load next (no guess-and-fetch).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentboard.storage.file_store import atomic_write

if TYPE_CHECKING:
    from agentboard.storage.file_store import FileStore


SESSION_BUDGET_TOK_DEFAULT = 500
CHAR_PER_TOK = 3.5
_TITLE_MAX_CHARS = 60
_TEASER_MAX_CHARS = 60


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class SessionWriter:
    """Writes session.md (index + teasers + status) for a run."""

    def __init__(
        self,
        store: "FileStore",
        budget_tok: int = SESSION_BUDGET_TOK_DEFAULT,
    ) -> None:
        self._store = store
        self._budget_chars = int(budget_tok * CHAR_PER_TOK)

    def _pile_dir(self, rid: str) -> Path:
        return self._store._run_pile_dir(rid)  # type: ignore[attr-defined]

    def _iter_count(self, rid: str) -> int:
        iters_dir = self._pile_dir(rid) / "iters"
        if not iters_dir.exists():
            return 0
        return len(list(iters_dir.glob("iter-*.json")))

    def _chapter_teaser(self, rid: str, chapter: str) -> str:
        """1-line teaser for a chapter. Best-effort — if chapter file
        does not yet exist, return a placeholder teaser.
        """
        path = self._pile_dir(rid) / "chapters" / f"{chapter}.md"
        if not path.exists():
            return f"(empty)"
        try:
            first_nonblank = next(
                (line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")),
                "(empty)",
            )
        except (OSError, UnicodeDecodeError):
            first_nonblank = "(unreadable)"
        return _truncate(first_nonblank, _TEASER_MAX_CHARS)

    def regen(
        self,
        rid: str,
        *,
        goal_title: str = "",
        current_phase: str = "?",
        total_steps: int = 0,
        last_verdict: str = "?",
    ) -> Path:
        """Regenerate session.md for a run."""
        title = _truncate(goal_title or f"session `{rid}`", _TITLE_MAX_CHARS)
        iter_count = self._iter_count(rid)

        chapters = ("contract", "labor", "verdict", "delta")
        teaser_lines = []
        for ch in chapters:
            teaser = self._chapter_teaser(rid, ch)
            teaser_lines.append(f"- **{ch}**: {teaser}")

        status_line = (
            f"**Status**: iter {iter_count}/{total_steps} · "
            f"phase `{current_phase}` · last verdict `{last_verdict}`"
        )

        content = "\n".join([
            f"# {title}",
            "",
            "## Chapters",
            *teaser_lines,
            "",
            "## Delta",
            "As-Is: (synth pending — M2 LLM overlay)",
            "To-Be: (synth pending — M2 LLM overlay)",
            "Diff:  (synth pending — M2 LLM overlay)",
            "",
            status_line,
        ])

        # If over budget, progressively shorten teasers then status
        if len(content) > self._budget_chars:
            # First pass: tighten teasers
            tighter = []
            for ch in chapters:
                t = _truncate(self._chapter_teaser(rid, ch), 12)
                tighter.append(f"- {ch}: {t}")
            content = "\n".join([
                f"# {_truncate(title, 30)}",
                "",
                "## Chapters",
                *tighter,
                "",
                status_line,
            ])

        session_path = self._pile_dir(rid) / "session.md"
        atomic_write(session_path, content)
        return session_path
