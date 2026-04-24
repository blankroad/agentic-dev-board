"""UserPromptSubmit hook — emits <system-reminder> with top-K relevant learnings.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §Data Flow — R3 auto-inject
mechanism. Hook stdout is injected into Claude Code model context (per A1 smoke
verification in s_001).
"""

from pathlib import Path

from agentboard.hooks_py import user_prompt_submit
from agentboard.storage.global_index import GlobalIndex


def test_emits_system_reminder_with_matching_learnings(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    GlobalIndex().register_learning(
        tmp_path / "proj-a",
        {"name": "sql-guardrail", "content": "never drop table in production", "tags": ["sql"]},
    )
    output = user_prompt_submit.main({"prompt": "help me drop table users"})
    assert "<system-reminder>" in output
    assert "</system-reminder>" in output
    assert "never drop table" in output


def test_truncates_output_to_2kb_at_learning_boundary(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    # arch.md edge: "truncate to 2KB at learning boundary, append
    # '...(N more via agentboard_search_learnings)'"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    idx = GlobalIndex()
    bulky = "X" * 600
    for i in range(5):
        idx.register_learning(
            tmp_path / f"proj-{i}",
            {
                "name": f"lesson-{i}",
                "content": f"keyword-match {bulky}",
                "tags": ["t"],
            },
        )
    output = user_prompt_submit.main({"prompt": "keyword-match"}, top_k=5)
    assert len(output.encode("utf-8")) <= 2048
    assert "more via agentboard_search_learnings" in output
