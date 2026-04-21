from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from agentboard.storage.file_store import FileStore


@dataclass
class Learning:
    """A learning entry with structured metadata (Phase H — Learnings 2.0)."""
    name: str
    content: str
    tags: list[str] = field(default_factory=list)
    category: str = "general"       # general | bug | pattern | constraint | style
    confidence: float = 0.5          # 0.0–1.0 — how strongly it should steer future work
    source: str = ""                 # goal_id or task_id that produced it
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_frontmatter(self) -> str:
        post = frontmatter.Post(
            self.content,
            name=self.name,
            tags=list(self.tags),
            category=self.category,
            confidence=self.confidence,
            source=self.source,
            created_at=self.created_at,
        )
        return frontmatter.dumps(post)

    @classmethod
    def from_file(cls, path: Path) -> "Learning":
        try:
            post = frontmatter.load(str(path))
            meta = post.metadata
            return cls(
                name=meta.get("name", path.stem),
                content=post.content.strip(),
                tags=list(meta.get("tags", [])),
                category=meta.get("category", "general"),
                confidence=float(meta.get("confidence", 0.5)),
                source=meta.get("source", ""),
                created_at=meta.get("created_at", ""),
            )
        except Exception:
            # Fallback for plain text files (backwards compat with Phase F)
            content = path.read_text().strip()
            return cls(name=path.stem, content=content)


def save_learning(
    store: FileStore,
    name: str,
    content: str,
    tags: list[str] | None = None,
    category: str = "general",
    confidence: float = 0.5,
    source: str = "",
) -> Path:
    learning = Learning(
        name=name, content=content,
        tags=tags or [], category=category,
        confidence=confidence, source=source,
    )
    path = store.save_learning(name, learning.to_frontmatter())
    return path


def load_all_learnings(store: FileStore) -> list[Learning]:
    return [Learning.from_file(p) for p in store.list_learnings()]


def load_relevant_learnings(store: FileStore, goal_description: str) -> str:
    """Phase H: uses retriever with tag boost."""
    from agentboard.memory.retriever import load_relevant_learnings as retriever_load
    return retriever_load(store, goal_description)


def search_learnings(
    store: FileStore,
    query: str,
    tag: str | None = None,
    category: str | None = None,
) -> list[Learning]:
    learnings = load_all_learnings(store)
    q_lower = query.lower().strip()
    results = []
    for l in learnings:
        if tag and tag not in l.tags:
            continue
        if category and l.category != category:
            continue
        if q_lower:
            hay = f"{l.name} {l.content} {' '.join(l.tags)} {l.category}".lower()
            if q_lower not in hay:
                continue
        results.append(l)
    # Sort by confidence desc
    results.sort(key=lambda l: -l.confidence)
    return results
