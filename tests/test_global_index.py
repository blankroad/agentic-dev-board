"""GlobalIndex — registry for ~/.agentboard/index/{projects,learnings,decisions}.jsonl.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 — Cross-Project Memory.
"""

import json
from pathlib import Path

from agentboard.storage import global_index


def test_register_project_appends_to_projects_jsonl(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    idx = global_index.GlobalIndex()
    project_root = tmp_path / "my-proj"
    idx.register_project(project_root)
    jsonl = fake_home / ".agentboard" / "index" / "projects.jsonl"
    assert jsonl.is_file()
    lines = jsonl.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["project_root"] == str(project_root)


def test_register_learning_appends_to_learnings_jsonl(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    idx = global_index.GlobalIndex()
    project_root = tmp_path / "proj"
    idx.register_learning(
        project_root,
        {"name": "foo-lesson", "content": "avoid bar", "tags": ["sql"]},
    )
    jsonl = fake_home / ".agentboard" / "index" / "learnings.jsonl"
    assert jsonl.is_file()
    entries = [json.loads(line) for line in jsonl.read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["name"] == "foo-lesson"
    assert entries[0]["project_root"] == str(project_root)


def test_search_learnings_returns_cross_project_keyword_matches(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    idx = global_index.GlobalIndex()
    proj_a = tmp_path / "a"
    proj_b = tmp_path / "b"
    idx.register_learning(
        proj_a,
        {"name": "sql-guardrail", "content": "never drop table", "tags": ["sql"]},
    )
    idx.register_learning(
        proj_b,
        {"name": "other", "content": "unrelated lore", "tags": ["misc"]},
    )
    results = idx.search_learnings(keyword="drop table")
    names = [r["name"] for r in results]
    assert "sql-guardrail" in names
    assert "other" not in names
