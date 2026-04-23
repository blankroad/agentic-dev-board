"""s_005 — payload.learnings must load from .agentboard/learnings/*.md files
via FileStore.list_learnings(), not the non-existent learnings.jsonl."""

from __future__ import annotations

from pathlib import Path


def test_learnings_loaded_from_md_files(tmp_path: Path) -> None:
    """Place a learning .md file in .agentboard/learnings/ and verify
    build_overview_payload surfaces it as payload.learnings[0]."""
    from agentboard.analytics.overview_payload import build_overview_payload
    from agentboard.models import BoardState, Goal, GoalStatus
    from agentboard.storage.file_store import FileStore

    (tmp_path / ".agentboard").mkdir()
    store = FileStore(tmp_path)
    board = BoardState(active_goal_id="g_l")
    board.goals.append(Goal(id="g_l", title="l", status=GoalStatus.active))
    store.save_board(board)
    goal_dir = tmp_path / ".agentboard" / "goals" / "g_l"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# plan\n")

    # Save a learning via FileStore's own API. Payload loader uses
    # list_learnings() which just lists .md files in the directory.
    body = (
        "---\n"
        "name: test-learning-one\n"
        "tags: [tui, pattern]\n"
        "category: pattern\n"
        "confidence: 0.7\n"
        "---\n\n"
        "# Test learning\n\n"
        "This is the body of the learning. It teaches a pattern.\n"
    )
    store.save_learning(name="test-learning-one", content=body)

    payload = build_overview_payload(tmp_path, "g_l", task_id=None)
    learnings = payload["learnings"]
    assert learnings, (
        f"expected at least one learning loaded from .md files, got: {learnings}"
    )
    names = [l.get("name") for l in learnings]
    assert "test-learning-one" in names, (
        f"learning named 'test-learning-one' missing from payload.learnings: {names}"
    )
