from __future__ import annotations

import json
from pathlib import Path

from agentboard.tui.anomaly import AnomalyClassifier


def test_classifier_handles_real_run_event_shape() -> None:
    """Base case: classifier parses every line of a real run file without
    raising. Non-anomaly events return None."""
    root = Path(__file__).resolve().parent.parent
    runs = sorted((root / ".agentboard" / "runs").glob("*.jsonl"))
    assert runs, "no runs/*.jsonl fixture available for schema spike"

    clf = AnomalyClassifier()
    total_lines = 0
    for path in runs[:3]:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            total_lines += 1
            result = clf.classify(record)
            assert result is None or (isinstance(result, tuple) and len(result) == 2)
    assert total_lines > 0


def test_redteam_broken_is_red() -> None:
    clf = AnomalyClassifier()
    assert clf.classify({"event": "redteam_complete", "state": {"verdict": "BROKEN"}}) == ("red", "redteam_broken")


def test_cso_insecure_is_orange() -> None:
    clf = AnomalyClassifier()
    assert clf.classify({"event": "cso_complete", "state": {"verdict": "INSECURE"}}) == ("orange", "cso_insecure")


def test_reviewer_fail_is_orange() -> None:
    clf = AnomalyClassifier()
    assert clf.classify({"event": "review_complete", "state": {"verdict": "FAIL"}}) == ("orange", "reviewer_fail")


def test_iter_gte_3_is_yellow() -> None:
    clf = AnomalyClassifier()
    assert clf.classify({"event": "iteration_complete", "state": {"iter": 3}}) == ("yellow", "retry_spike")
    assert clf.classify({"event": "iteration_complete", "state": {"iter": 5}}) == ("yellow", "retry_spike")
    assert clf.classify({"event": "iteration_complete", "state": {"iter": 2}}) is None


def test_classify_tolerates_non_dict_records() -> None:
    """Red-team A2: json.loads may return None/int/str/list for lines like
    'null\\n', '42\\n', etc. Classifier must return None, not raise."""
    clf = AnomalyClassifier()
    for bad in (None, 42, "oops", [1, 2, 3], True):
        assert clf.classify(bad) is None, f"classify({bad!r}) should return None"
