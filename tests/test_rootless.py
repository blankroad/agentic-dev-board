"""Rootless-mode routing for save_learning when project_root is absent.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 — MCP tools with project_root=None
land on ~/.agentboard/ global index instead of erroring.
"""

from pathlib import Path

from agentboard.memory import rootless


def test_save_learning_rootless_none_writes_to_global_index(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    rootless.save_learning_rootless(
        project_root=None,
        name="no-root-lesson",
        content="some truth",
        tags=["x"],
    )
    idx_path = fake_home / ".agentboard" / "index" / "learnings.jsonl"
    assert idx_path.is_file()
    assert "no-root-lesson" in idx_path.read_text()


def test_relevant_learnings_from_project_b_returns_project_a_entry(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    from agentboard.storage.global_index import GlobalIndex

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    proj_a = tmp_path / "proj-a"
    proj_b = tmp_path / "proj-b"
    idx = GlobalIndex()
    idx.register_learning(
        proj_a,
        {"name": "A-lesson", "content": "avoid drop table in production", "tags": ["sql"]},
    )
    results = rootless.relevant_learnings_rootless(
        goal_description="drop table",
        project_root=proj_b,
    )
    assert any(
        r["name"] == "A-lesson" and r["project_root"] == str(proj_a) for r in results
    )
