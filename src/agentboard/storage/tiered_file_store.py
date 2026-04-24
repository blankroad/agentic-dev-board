"""Tier 1 dual-write facade — composes FileStore (project-local truth) with
GlobalIndex (cross-project mirror). FileStore itself stays unchanged per
arch.md ("신규 GlobalStore가 기존 FileStore를 래핑").
"""

from pathlib import Path

from agentboard.storage.file_store import FileStore
from agentboard.storage.global_index import GlobalIndex


class TieredFileStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._fs = FileStore(project_root)
        self._index = GlobalIndex()

    def save_learning(
        self,
        name: str,
        content: str,
        tags: list[str] | None = None,
    ) -> Path:
        local_path = self._fs.save_learning(name, content)
        self._index.register_learning(
            self.project_root,
            {"name": name, "content": content, "tags": tags or []},
        )
        return local_path
