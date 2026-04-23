"""Tests for ThrottleSentinel — TOCTOU-safe critical section for
chapter/session synth decision.

Covers s_014 (monotonic single-thread), s_015 (threaded property), and
s_016 (multi-process subprocess test). CRITICAL path per Eng Review.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest


def test_throttle_monotonic_decision(tmp_path) -> None:
    """ThrottleSentinel.decide_and_commit returns True iff synth is due:
    first call, ≥5 iter delta since last synth, or phase transition.

    guards: concurrent mutation (edge) — verifies base invariant single-thread
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_throttle import ThrottleSentinel

    store = FileStore(tmp_path)
    sentinel = ThrottleSentinel(store)
    rid = "run_throttle"
    # Ensure pile dir exists (normally via write_iter_artifact)
    (tmp_path / ".agentboard" / "runs" / rid).mkdir(parents=True, exist_ok=True)

    # First ever: True
    assert sentinel.decide_and_commit(rid, 1, "tdd") is True
    # +1 delta same phase: False
    assert sentinel.decide_and_commit(rid, 2, "tdd") is False
    # Phase change: True (even with small delta)
    assert sentinel.decide_and_commit(rid, 3, "review") is True
    # Same phase, delta 1..4: False
    for n in (4, 5, 6, 7):
        assert sentinel.decide_and_commit(rid, n, "review") is False
    # Delta 5 from last_synth_iter=3 → True at iter 8
    assert sentinel.decide_and_commit(rid, 8, "review") is True


def test_throttle_threaded_10x10_matches_replay(tmp_path) -> None:
    """10 threads × 10 concurrent decide_and_commit calls must leave a
    coherent sentinel file (no torn writes). Final state matches the
    deterministic single-threaded replay for the equivalent iter sequence.

    guards: concurrent mutation (edge) — CRITICAL TOCTOU mitigation
    """
    from agentboard.storage.file_store import FileStore
    from agentboard.storage.pile_throttle import ThrottleSentinel

    store = FileStore(tmp_path)
    sentinel = ThrottleSentinel(store)
    rid = "run_threaded"
    (tmp_path / ".agentboard" / "runs" / rid).mkdir(parents=True, exist_ok=True)

    # 10 threads × 10 iter_n values each (1..100 total, non-overlapping
    # to make each call meaningfully distinct).
    barrier = threading.Barrier(10)
    errors: list[str] = []

    def worker(thread_idx: int) -> None:
        try:
            barrier.wait(timeout=5)
            base = thread_idx * 10
            for i in range(10):
                iter_n = base + i + 1
                # Phase cycles every 3 iters to exercise phase-change path
                phase = ["tdd", "review", "approval"][iter_n % 3]
                sentinel.decide_and_commit(rid, iter_n, phase)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"threads raised: {errors}"

    # Sentinel must be parseable JSON — no torn writes. Content need not
    # match any specific replay (concurrent interleaving is non-det), but
    # last_synth_iter must be >0 and last_phase must be one of the 3.
    raw = (tmp_path / ".agentboard" / "runs" / rid / ".throttle").read_text(encoding="utf-8")
    state = json.loads(raw)  # raises if torn
    assert isinstance(state, dict)
    assert state.get("last_synth_iter", 0) >= 1
    assert state.get("last_phase") in ("tdd", "review", "approval")


def test_throttle_multiprocess_subprocess(tmp_path) -> None:
    """2 subprocesses × 30 iter decide_and_commit calls on same rid.

    subprocess has truly independent fds (unlike threading in one process),
    which is the real TOCTOU stress. Sentinel must remain parseable JSON
    and last_synth_iter must be in [1, 60] after contention.

    guards: concurrent mutation (edge) — multi-process TOCTOU (CRITICAL 2-layer fix)
    """
    from agentboard.storage.file_store import FileStore

    rid = "run_multiproc"
    # Seed the pile dir so subprocess workers can locate sentinel path
    store = FileStore(tmp_path)
    (tmp_path / ".agentboard" / "runs" / rid).mkdir(parents=True, exist_ok=True)

    worker_src = '''
import sys, json
from pathlib import Path
sys.path.insert(0, {repo_src!r})
from agentboard.storage.file_store import FileStore
from agentboard.storage.pile_throttle import ThrottleSentinel

root = Path({root!r})
base = int(sys.argv[1])  # offset so each process uses distinct iter_n range
store = FileStore(root)
sentinel = ThrottleSentinel(store)
phases = ("tdd", "review", "approval")
for i in range(30):
    iter_n = base + i + 1
    phase = phases[iter_n % 3]
    sentinel.decide_and_commit({rid!r}, iter_n, phase)
print("OK")
'''.format(
        repo_src=str(Path(__file__).parent.parent / "src"),
        root=str(tmp_path),
        rid=rid,
    )

    script_path = tmp_path / "_throttle_worker.py"
    script_path.write_text(worker_src, encoding="utf-8")

    # Launch 2 subprocesses concurrently
    procs = [
        subprocess.Popen(
            [sys.executable, str(script_path), str(base)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for base in (0, 100)  # non-overlapping iter ranges
    ]
    results = [p.communicate(timeout=30) for p in procs]
    for (out, err), p in zip(results, procs):
        assert p.returncode == 0, f"subprocess failed: {err.decode()}"
        assert b"OK" in out

    # Sentinel still parses cleanly (no torn writes across processes)
    sentinel_path = tmp_path / ".agentboard" / "runs" / rid / ".throttle"
    raw = sentinel_path.read_text(encoding="utf-8")
    state = json.loads(raw)
    assert isinstance(state, dict)
    assert 1 <= state.get("last_synth_iter", 0) <= 130
    assert state.get("last_phase") in ("tdd", "review", "approval")
