from __future__ import annotations

import re
from pathlib import Path

from agentboard.storage.file_store import FileStore


def load_relevant_learnings(store: FileStore, goal_description: str, max_learnings: int = 5) -> str:
    """Load learnings most relevant to the goal, ranked by keyword overlap + tag match + confidence.

    Phase H upgrade:
    - Frontmatter-aware: parses tags/category/confidence
    - Score = keyword_jaccard + 0.3 × tag_jaccard + 0.2 × confidence
    """
    from agentboard.memory.learnings import load_all_learnings
    learnings = load_all_learnings(store)
    if not learnings:
        return ""

    goal_tokens = _tokenize(goal_description)
    scored: list[tuple[float, object]] = []

    for l in learnings:
        content_tokens = _tokenize(l.content) | _tokenize(l.name)
        tag_tokens = {t.lower() for t in l.tags}

        # Keyword overlap (jaccard)
        overlap = len(goal_tokens & content_tokens)
        union = len(goal_tokens | content_tokens) or 1
        kw_score = overlap / union

        # Tag overlap (jaccard) — tags count as stronger signal
        tag_overlap = len(goal_tokens & tag_tokens)
        tag_union = len(goal_tokens | tag_tokens) or 1
        tag_score = tag_overlap / tag_union

        conf = max(0.0, min(1.0, l.confidence))
        score = kw_score + 0.3 * tag_score + 0.2 * conf

        scored.append((score, l))

    scored.sort(key=lambda x: -x[0])
    top = [l for score, l in scored[:max_learnings] if score > 0.01]
    if not top:
        return ""

    parts = []
    for l in top:
        tag_str = f"  [tags: {', '.join(l.tags)}]" if l.tags else ""
        parts.append(f"### {l.name}{tag_str}\n{l.content}")
    return "\n\n".join(parts)


def promote_learning(
    store: FileStore,
    name: str,
    content: str,
    auto: bool = False,
    tags: list[str] | None = None,
    category: str = "general",
    confidence: float = 0.5,
    source: str = "",
) -> Path | None:
    if not content.strip():
        return None
    from agentboard.memory.learnings import save_learning
    return save_learning(
        store, name, content,
        tags=tags or ([category] if category != "general" else []),
        category=category,
        confidence=confidence,
        source=source,
    )


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 2}
