from __future__ import annotations

from typing import Optional

AnomalyResult = tuple[str, str]  # (color, kind)


class AnomalyClassifier:
    """Single source of anomaly rules. Used by TailWorker, LiveStreamView,
    HealthBar. Pure function — no state. See arch.md anomaly table."""

    _VERDICT_RULES: dict[tuple[str, str], AnomalyResult] = {
        ("redteam_complete", "BROKEN"): ("red", "redteam_broken"),
        ("cso_complete", "INSECURE"): ("orange", "cso_insecure"),
        ("review_complete", "FAIL"): ("orange", "reviewer_fail"),
    }

    def classify(self, record: object) -> Optional[AnomalyResult]:
        # Red-team A2: json.loads can yield None/int/str/list from malformed
        # or non-object JSON lines. Non-dict records are never anomalies.
        if not isinstance(record, dict):
            return None
        event = record.get("event")
        raw_state = record.get("state")
        state = raw_state if isinstance(raw_state, dict) else {}

        verdict = state.get("verdict")
        if isinstance(event, str) and isinstance(verdict, str):
            hit = self._VERDICT_RULES.get((event, verdict))
            if hit is not None:
                return hit

        if event == "iteration_complete":
            itr = state.get("iter")
            if isinstance(itr, int) and itr >= 3:
                return ("yellow", "retry_spike")

        return None
