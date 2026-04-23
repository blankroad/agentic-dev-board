"""Schema versioning for M1a-plumbing pile JSONs (p_001-p_003).

Guards future M2 changes from silently breaking M1a consumers. Missing
field on older pile files is treated as schema_version=0 by readers.
"""
from __future__ import annotations

import json
import re


def test_iter_json_has_schema_version_v1(tmp_path) -> None:
    from agentboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    store.write_iter_artifact("run_v", 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    path = tmp_path / ".agentboard" / "runs" / "run_v" / "iters" / "iter-001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema_version") == 1, f"iter.json missing schema_version: {data}"


def test_digest_has_schema_version_and_idempotent(tmp_path) -> None:
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_digest import DigestWriter

    store = FileStore(tmp_path)
    store.write_iter_artifact("run_d", 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    writer = DigestWriter(store)
    writer.update("run_d")
    path = tmp_path / ".agentboard" / "runs" / "run_d" / "digest.json"
    first = path.read_bytes()
    data = json.loads(first)
    assert data.get("schema_version") == 1
    # Idempotency still holds with the new field present
    writer.update("run_d")
    assert path.read_bytes() == first


def test_session_md_frontmatter_schema_version(tmp_path) -> None:
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_session import SessionWriter

    store = FileStore(tmp_path)
    store.write_iter_artifact("run_s", 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    SessionWriter(store).regen(
        "run_s", goal_title="Test", current_phase="tdd_red",
        total_steps=5, last_verdict="RED",
    )
    content = (tmp_path / ".agentboard" / "runs" / "run_s" / "session.md").read_text(encoding="utf-8")
    # Frontmatter or dedicated line — accept either `---\nschema_version: 1\n---`
    # or an inline marker at the top. Test just asserts the presence.
    assert re.search(r"schema_version:\s*1", content), (
        f"session.md missing schema_version: 1 marker, got:\n{content[:300]}"
    )
