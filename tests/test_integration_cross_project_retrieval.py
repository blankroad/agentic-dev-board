"""Goal checklist #2 — Project A save_learning → Project B relevant_learnings.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 goal_checklist item 2.

Frames s_019's cross-project retrieval as an end-to-end CHECKLIST gate: the
save happens via rootless.save_learning_rootless(project_root=A), retrieval
via rootless.relevant_learnings_rootless(project_root=B).
"""

from pathlib import Path

from agentboard.memory import rootless


def test_project_a_learning_surfaces_in_project_b_retrieval(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    proj_a = tmp_path / "proj-a"
    proj_a.mkdir()
    (proj_a / ".agentboard").mkdir()
    proj_b = tmp_path / "proj-b"
    proj_b.mkdir()
    (proj_b / ".agentboard").mkdir()

    # Project A saves a learning.
    rootless.save_learning_rootless(
        project_root=proj_a,
        name="cross-project-lesson",
        content="avoid writing to real home dir",
        tags=["memory-test"],
    )

    # Project B's retrieval surfaces it.
    results = rootless.relevant_learnings_rootless(
        goal_description="writing to home directory",
        project_root=proj_b,
    )
    assert any(r.get("name") == "cross-project-lesson" for r in results)
