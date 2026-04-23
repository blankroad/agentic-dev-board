"""Tests for FileStore pile-aware helpers + DigestWriter + ChapterWriter + SessionWriter.

Covers M1a-data atomic steps s_008 through s_018. Each test is scoped
to a single behavior per TDD discipline.
"""
from __future__ import annotations

import json

import pytest


def test_write_iter_artifact_atomic(tmp_path) -> None:
    """FileStore.write_iter_artifact writes runs/<rid>/iters/iter-NNN.json
    atomically via existing atomic_write primitive.
    """
    from agentboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    rid = "run_test123"
    data = {
        "phase": "tdd_red",
        "iter_n": 1,
        "ts": "2026-01-01T00:00:00Z",
        "duration_ms": 100,
        "test_result": "red",
    }

    store.write_iter_artifact(rid, 1, data)

    path = tmp_path / ".agentboard" / "runs" / rid / "iters" / "iter-001.json"
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    # M1a-plumbing adds schema_version: 1 alongside caller payload.
    # The rest of the payload must round-trip unchanged.
    assert loaded["schema_version"] == 1
    for k, v in data.items():
        assert loaded[k] == v


def test_rid_index_dir_first_and_self_heal(tmp_path) -> None:
    """rid-index update order: run dir created before .rid_index.json.

    Also: load_run returns None when index entry exists but dir is missing
    (triggers self-heal signal for rebuild-pile in M1a-plumbing).
    """
    from agentboard.storage.file_store import FileStore

    store = FileStore(tmp_path)
    gid = "g_test"
    tid = "t_test"
    rid = "run_abc"
    # Register rid by writing first iter. This must also populate rid-index.
    store.write_iter_artifact(rid, 1, {"phase": "tdd_red", "iter_n": 1}, gid=gid, tid=tid)

    # Index should exist with our rid
    idx_path = tmp_path / ".agentboard" / ".rid_index.json"
    assert idx_path.exists()
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    assert rid in idx
    assert idx[rid]["gid"] == gid
    assert idx[rid]["tid"] == tid

    # load_run returns the run path when dir exists
    run_info = store.load_run(rid)
    assert run_info is not None
    assert run_info["rid"] == rid

    # Simulate orphan state: delete the run dir but keep the index entry
    pile_dir = tmp_path / ".agentboard" / "runs" / rid
    import shutil
    shutil.rmtree(pile_dir)
    assert not pile_dir.exists()

    # load_run must return None (signals self-heal needed), not raise
    assert store.load_run(rid) is None


def test_sanitize_id_rejects_traversal_rid(tmp_path) -> None:
    """_sanitize_id must reject rid with .. or / or \\ before any path op.

    guards: path traversal defense (security)
    """
    from agentboard.storage.file_store import FileStore

    store = FileStore(tmp_path)

    # Traversal via ..
    with pytest.raises(ValueError, match="Unsafe id"):
        store.write_iter_artifact("../etc/passwd", 1, {"phase": "tdd_red"})

    # Forward slash
    with pytest.raises(ValueError, match="Unsafe id"):
        store.write_iter_artifact("run/with/slash", 1, {"phase": "tdd_red"})

    # Backslash
    with pytest.raises(ValueError, match="Unsafe id"):
        store.write_iter_artifact("run\\with\\backslash", 1, {"phase": "tdd_red"})

    # load_run with traversal rid
    with pytest.raises(ValueError, match="Unsafe id"):
        store.load_run("../../../etc")


def test_is_relative_to_defense(tmp_path) -> None:
    """is_relative_to post-resolve guard catches crafted index / symlink
    attacks where a seemingly-safe rid resolves outside .agentboard.

    guards: path traversal defense (security, defense-in-depth)
    """
    from agentboard.storage.file_store import FileStore

    store = FileStore(tmp_path)

    # Plant a crafted index pointing outside .agentboard (e.g. /etc)
    (tmp_path / ".agentboard").mkdir(exist_ok=True)
    crafted = {"run_evil": {"gid": "g", "tid": "t"}}
    (tmp_path / ".agentboard" / ".rid_index.json").write_text(
        json.dumps(crafted), encoding="utf-8"
    )
    # But also make a dir that symlinks outside
    outside = tmp_path.parent / "escape_target"
    outside.mkdir(exist_ok=True)
    runs_dir = tmp_path / ".agentboard" / "runs"
    runs_dir.mkdir(exist_ok=True)
    try:
        (runs_dir / "run_evil").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")

    # load_run must verify resolved path stays under .agentboard
    info = store.load_run("run_evil")
    assert info is None, "load_run must refuse resolved-path escape"


def test_digest_iter_count_idempotent(tmp_path) -> None:
    """DigestWriter.update recomputes iter_count from glob(iters/iter-*.json).

    Running update N times on the same pile must produce byte-identical
    digest.json. No increment counter.

    guards: cached stale (edge)
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_digest import DigestWriter

    store = FileStore(tmp_path)
    rid = "run_digest"
    store.write_iter_artifact(rid, 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    store.write_iter_artifact(rid, 2, {"phase": "tdd_green", "iter_n": 2}, gid="g", tid="t")
    store.write_iter_artifact(rid, 3, {"phase": "tdd_refactor", "iter_n": 3}, gid="g", tid="t")

    writer = DigestWriter(store)
    writer.update(rid)
    digest_path = tmp_path / ".agentboard" / "runs" / rid / "digest.json"
    assert digest_path.exists()
    first = digest_path.read_bytes()

    # Multiple update calls → byte-identical output
    writer.update(rid)
    writer.update(rid)
    assert digest_path.read_bytes() == first

    # iter_count = glob count
    digest = json.loads(first)
    assert digest["iter_count"] == 3
    assert digest["rid"] == rid


def test_digest_per_file_scrubber_fold(tmp_path) -> None:
    """DigestWriter folds per_file_scrubber_delta across iters into a
    path → list mapping (append-only, chronological order by iter_n).
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_digest import DigestWriter

    store = FileStore(tmp_path)
    rid = "run_scrub"

    store.write_iter_artifact(rid, 1, {
        "phase": "tdd_red",
        "iter_n": 1,
        "per_file_scrubber_delta": {"src/foo.py": "red"},
    }, gid="g", tid="t")
    store.write_iter_artifact(rid, 2, {
        "phase": "tdd_green",
        "iter_n": 2,
        "per_file_scrubber_delta": {"src/foo.py": "green", "src/bar.py": "green"},
    }, gid="g", tid="t")
    store.write_iter_artifact(rid, 3, {
        "phase": "tdd_refactor",
        "iter_n": 3,
        "per_file_scrubber_delta": {"src/bar.py": "refactor"},
    }, gid="g", tid="t")

    writer = DigestWriter(store)
    writer.update(rid)
    digest = json.loads(
        (tmp_path / ".agentboard" / "runs" / rid / "digest.json").read_text(encoding="utf-8")
    )

    # foo.py touched in iters 1 and 2
    assert digest["per_file_scrubber"]["src/foo.py"] == ["red", "green"]
    # bar.py touched in iters 2 and 3
    assert digest["per_file_scrubber"]["src/bar.py"] == ["green", "refactor"]


def test_digest_iter_count_skips_corrupt_iters(tmp_path) -> None:
    """F1 (redteam finding): DigestWriter.iter_count must reflect USABLE
    iters (parseable JSON), not the raw glob count. Corrupt iter.json
    files should be skipped from both content AND the count — otherwise
    consumer sees iter_count=N but chapter/session only show M<N iters.

    guards: state corruption (redteam F1 mitigation)
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_digest import DigestWriter

    store = FileStore(tmp_path)
    rid = "run_corrupt"
    # 3 valid iters
    store.write_iter_artifact(rid, 1, {"phase": "tdd_red", "iter_n": 1}, gid="g", tid="t")
    store.write_iter_artifact(rid, 2, {"phase": "tdd_green", "iter_n": 2}, gid="g", tid="t")
    store.write_iter_artifact(rid, 3, {"phase": "tdd_red", "iter_n": 3}, gid="g", tid="t")

    # Corrupt iter-002.json (simulates partial write / external tampering)
    corrupt_path = tmp_path / ".agentboard" / "runs" / rid / "iters" / "iter-002.json"
    corrupt_path.write_text("this is not valid json {", encoding="utf-8")

    DigestWriter(store).update(rid)
    digest = json.loads(
        (tmp_path / ".agentboard" / "runs" / rid / "digest.json").read_text(encoding="utf-8")
    )

    # Glob still sees 3 files, but only 2 are usable
    assert digest["iter_count"] == 2, (
        f"iter_count must reflect usable iters (got {digest['iter_count']}, expected 2)"
    )
    # Optional: expose raw_iter_count for auditing — if present, must equal 3
    if "raw_iter_count" in digest:
        assert digest["raw_iter_count"] == 3


def test_chapter_drops_oldest_verdicts_when_tight_budget_all_verdict(tmp_path) -> None:
    """F3 fix (redteam): ChapterWriter must respect budget even when
    all iters are verdict and first-line truncation is insufficient.
    Fallback: drop oldest verdict iters with an aggregate marker.
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter

    store = FileStore(tmp_path)
    rid = "run_tight_verdict"

    # 50 redteam iters — all verdict, no tdd iters to collapse
    for i in range(1, 51):
        store.write_iter_artifact(
            rid, i,
            {
                "phase": "redteam",
                "iter_n": i,
                "ts": "2026-01-01T00:00:00Z",
                "duration_ms": 2000,
                "verdict": "BROKEN",
                "findings": [f"finding text line {j}" for j in range(5)],
                "scenarios_tested": 5,
            },
            gid="g", tid="t",
        )

    # Very tight budget — 200 tok ~ 700 chars, way below 50 iters' worth
    tight = ChapterWriter(store, budget_tok=200)
    tight_path = tight.regen_labor(rid)
    content = tight_path.read_text(encoding="utf-8")

    # Contract: output must not exceed budget chars
    assert len(content) <= 200 * 3.5 + 200, (  # +200 grace for header/marker
        f"ChapterWriter exceeded tight budget: {len(content)} chars"
    )
    # At least the most recent verdict iter (iter 50) must survive
    assert "iter 50" in content
    # Aggregate marker for dropped older verdicts
    assert "dropped" in content.lower() or "aggregate" in content.lower()


def test_chapter_labor_regen_with_truncation(tmp_path) -> None:
    """ChapterWriter.regen_labor: write labor.md from iter artifacts.
    Truncate greedy-from-oldest non-verdict iters when over budget.
    Verdict iters (redteam/approval) always pinned.
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter

    store = FileStore(tmp_path)
    rid = "run_chapter"

    # 45 tdd iters (non-verdict) + 3 redteam + 2 approval = 50 total.
    for i in range(1, 46):
        store.write_iter_artifact(
            rid, i,
            {
                "phase": "tdd_green" if i % 2 == 0 else "tdd_red",
                "iter_n": i,
                "ts": "2026-01-01T00:00:00Z",
                "duration_ms": 100,
                "test_result": "green" if i % 2 == 0 else "red",
                "diff_ref": f"runs/x/changes/iter-{i}.diff",
                "passed": 10 if i % 2 == 0 else 0,
                "failed": 0 if i % 2 == 0 else 1,
            },
            gid="g", tid="t",
        )
    for i in (46, 47, 48):
        store.write_iter_artifact(
            rid, i,
            {
                "phase": "redteam",
                "iter_n": i,
                "ts": "2026-01-01T00:00:00Z",
                "duration_ms": 2000,
                "verdict": "SURVIVED",
                "findings": [],
                "scenarios_tested": 3,
            },
            gid="g", tid="t",
        )
    for i in (49, 50):
        store.write_iter_artifact(
            rid, i,
            {
                "phase": "approval",
                "iter_n": i,
                "ts": "2026-01-01T00:00:00Z",
                "duration_ms": 500,
                "verdict": "APPROVED",
                "squash_policy": "squash",
            },
            gid="g", tid="t",
        )

    writer = ChapterWriter(store)
    path = writer.regen_labor(rid)
    assert path.exists()
    content = path.read_text(encoding="utf-8")

    # Budget: 3k tok = 10500 chars
    assert len(content) / 3.5 <= 3000, f"chapter too long: {len(content)} chars"

    # Verdict iters (redteam 46-48, approval 49-50) must appear regardless of truncation.
    for n in (46, 47, 48, 49, 50):
        assert f"iter {n}" in content, f"verdict iter {n} missing (pin violation)"

    # Tight-budget truncation: override budget to force collapse
    tight = ChapterWriter(store, budget_tok=100)
    tight_path = tight.regen_labor(rid)
    tight_content = tight_path.read_text(encoding="utf-8")
    assert len(tight_content) / 3.5 <= 100 * 1.2, (
        f"tight budget not enforced: {len(tight_content)} chars"
    )
    # Even under tight budget, some verdict iters must survive
    assert any(f"iter {n}" in tight_content for n in (46, 47, 48, 49, 50)), (
        "all verdict iters truncated — pin rule violated"
    )


def test_session_md_budget_and_teasers(tmp_path) -> None:
    """SessionWriter produces session.md ≤500 tok with:
    - header title
    - per-chapter 1-line teaser (for agent discovery)
    - 3-line As-Is → To-Be delta placeholder
    - status line (iter N/M · phase · last verdict)
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_chapter import ChapterWriter
    from agentboard.storage.pile_session import SessionWriter

    store = FileStore(tmp_path)
    rid = "run_session"

    # Seed 5 iters + regen labor chapter (realistic pile state)
    for i in range(1, 6):
        store.write_iter_artifact(
            rid, i,
            {
                "phase": "tdd_green" if i % 2 == 0 else "tdd_red",
                "iter_n": i,
                "ts": "2026-01-01T00:00:00Z",
                "duration_ms": 100,
                "test_result": "green" if i % 2 == 0 else "red",
                "diff_ref": f"runs/x/iter-{i}.diff",
                "passed": 10 if i % 2 == 0 else 0,
                "failed": 0 if i % 2 == 0 else 1,
            },
            gid="g", tid="t",
        )
    ChapterWriter(store).regen_labor(rid)

    writer = SessionWriter(store)
    path = writer.regen(
        rid,
        goal_title="Test Goal Title",
        current_phase="tdd_green",
        total_steps=22,
        last_verdict="GREEN",
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")

    # ≤500 tok ≈ 1750 chars
    assert len(content) / 3.5 <= 500, f"session.md too long: {len(content)} chars"

    # Required structural elements
    assert "Test Goal Title" in content or "session `run_session`" in content
    # Per-chapter teasers with counts (agent discovery gate — DX Pass 7 fix)
    assert "labor" in content.lower()
    assert "contract" in content.lower()
    assert "verdict" in content.lower()
    assert "delta" in content.lower()
    # Status line
    assert "iter 5/22" in content or "5 / 22" in content
    assert "tdd_green" in content
    assert "GREEN" in content
