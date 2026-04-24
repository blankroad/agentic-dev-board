"""Registry for ~/.agentboard/index/{projects,learnings,decisions}.jsonl.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §"Architecture Overview".
Tracks registered projects + surfaces learnings/decisions across projects for
R3 auto-inject and relevant-learnings lookup.
"""

import json
from pathlib import Path


class GlobalIndex:
    def __init__(self) -> None:
        self.root = Path.home() / ".agentboard" / "index"
        self.root.mkdir(parents=True, exist_ok=True)

    def register_project(self, project_root: Path) -> None:
        target = self.root / "projects.jsonl"
        with target.open("a") as f:
            f.write(json.dumps({"project_root": str(project_root)}) + "\n")

    def register_learning(self, project_root: Path, learning: dict) -> None:
        target = self.root / "learnings.jsonl"
        entry = {"project_root": str(project_root), **learning}
        with target.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def search_learnings(
        self, keyword: str = "", tags: list[str] | None = None
    ) -> list[dict]:
        target = self.root / "learnings.jsonl"
        if not target.is_file():
            return []
        results: list[dict] = []
        # Token-level match: any word from keyword appearing in name+content
        # counts as a hit. Short tokens (≤2 chars) skipped to avoid noise like
        # "a", "I", "be" false-matching unrelated entries.
        kw_tokens = [
            tok.strip(".,!?:;'\"()[]{}").lower()
            for tok in keyword.split()
            if tok.strip() and len(tok.strip(".,!?:;'\"()[]{}")) > 2
        ]
        tag_set = set(tags or [])
        for line in target.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # arch.md edge #11 — fail-closed on corrupt line, continue scan.
                continue
            haystack = f"{entry.get('name', '')} {entry.get('content', '')}".lower()
            if kw_tokens and not any(t in haystack for t in kw_tokens):
                continue
            if tag_set and not tag_set.intersection(entry.get("tags", [])):
                continue
            results.append(entry)
        return results
