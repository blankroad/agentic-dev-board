"""Rootless routing — MCP tool called with project_root=None lands on global index.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §"MCP 서버는 project_root=None
fallback으로 rootless mode를 지원". Tier 1 callers (project_root set) continue to use
the existing FileStore path via memory.learnings.save_learning.
"""

from pathlib import Path

from agentboard.config import resolve_project_root
from agentboard.storage.global_index import GlobalIndex


def save_learning_rootless(
    project_root: Path | None,
    name: str,
    content: str,
    tags: list[str] | None = None,
    category: str = "general",
    confidence: float = 0.5,
    source: str = "",
) -> None:
    if project_root is None:
        GlobalIndex().register_learning(
            resolve_project_root(None),
            {
                "name": name,
                "content": content,
                "tags": tags or [],
                "category": category,
                "confidence": confidence,
                "source": source,
            },
        )
        return
    # Tier 1 mode: project-local truth + global mirror write-through.
    from agentboard.memory.learnings import save_learning as _save_learning
    from agentboard.storage.file_store import FileStore

    _save_learning(
        FileStore(project_root),
        name,
        content,
        tags=tags,
        category=category,
        confidence=confidence,
        source=source,
    )
    GlobalIndex().register_learning(
        project_root,
        {
            "name": name,
            "content": content,
            "tags": tags or [],
            "category": category,
            "confidence": confidence,
            "source": source,
        },
    )


def relevant_learnings_rootless(
    goal_description: str,
    project_root: Path | None = None,
) -> list[dict]:
    """Cross-project lookup — always consult the global learnings index.

    project_root is accepted for API symmetry with the MCP tool but not
    required to constrain results; the whole point of R3 auto-inject is
    that learnings from other projects surface in the current session.
    """
    del project_root  # unused — retrieval is global-scope by design.
    return GlobalIndex().search_learnings(keyword=goal_description)
