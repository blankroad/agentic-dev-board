"""Tier 1 mirror write-through — project-local FileStore + GlobalIndex mirror.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §"신규 GlobalStore가
기존 FileStore를 래핑해 dual-write routing을 담당". This TieredFileStore
composes the existing FileStore (unchanged) with a global-index mirror so
Tier 1 save operations land in both places.
"""

from pathlib import Path

from agentboard.storage import tiered_file_store


def test_save_learning_mirrors_to_global_index_in_tier1_mode(
    tmp_path: Path, monkeypatch: "object"
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    project_root = tmp_path / "proj"
    project_root.mkdir()
    fs = tiered_file_store.TieredFileStore(project_root=project_root)
    fs.save_learning("L1", "some content", tags=["sql"])
    global_idx = fake_home / ".agentboard" / "index" / "learnings.jsonl"
    assert global_idx.is_file()
    text = global_idx.read_text()
    assert "L1" in text
    assert str(project_root) in text
