"""FM6 integration — user-scope + project-scope hooks both fire; their learning
sets surface jointly without either being dedup'd away.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 challenge.md Failure Mode 6.

Different from decisions.jsonl dedup (goal_checklist #4), learnings are
content-level distinct across hook sources — retrieval must return BOTH.
"""

from pathlib import Path

from agentboard.storage.global_index import GlobalIndex


def test_user_and_project_hook_learning_sets_both_surface(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    idx = GlobalIndex()
    project_root = tmp_path / "proj"

    idx.register_learning(
        project_root,
        {
            "name": "user-scope-lesson",
            "content": "teachable moment about X",
            "tags": ["user-hook"],
            "source": "user_hook",
        },
    )
    idx.register_learning(
        project_root,
        {
            "name": "project-scope-lesson",
            "content": "teachable moment about Y",
            "tags": ["project-hook"],
            "source": "project_hook",
        },
    )

    results = idx.search_learnings(keyword="teachable moment")
    names = {r.get("name") for r in results}
    assert "user-scope-lesson" in names
    assert "project-scope-lesson" in names
