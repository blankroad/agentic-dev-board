"""Typed PhaseData dataclasses for phase-typed rendering.

Discriminator base + per-phase subtypes. Runtime validation for Literal
fields is enforced in __post_init__ since the stdlib does not check
Literal types at dataclass construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class PhaseDataBase:
    phase: str
    iter_n: int
    ts: str
    duration_ms: int


_TDD_RESULTS = ("red", "green", "refactor")


@dataclass
class TddIterData(PhaseDataBase):
    test_result: Literal["red", "green", "refactor"]
    diff_ref: str
    passed: int
    failed: int

    def __post_init__(self) -> None:
        if self.test_result not in _TDD_RESULTS:
            raise ValueError(
                f"test_result must be one of {_TDD_RESULTS}, got {self.test_result!r}"
            )


_REDTEAM_VERDICTS = ("SURVIVED", "BROKEN")


@dataclass
class RedteamData(PhaseDataBase):
    verdict: Literal["SURVIVED", "BROKEN"]
    findings: list[str]
    scenarios_tested: int

    def __post_init__(self) -> None:
        if self.verdict not in _REDTEAM_VERDICTS:
            raise ValueError(
                f"verdict must be one of {_REDTEAM_VERDICTS}, got {self.verdict!r}"
            )


_APPROVAL_VERDICTS = ("APPROVED", "REJECTED", "PENDING")


@dataclass
class ApprovalData(PhaseDataBase):
    verdict: Literal["APPROVED", "REJECTED", "PENDING"]
    squash_policy: str

    def __post_init__(self) -> None:
        if self.verdict not in _APPROVAL_VERDICTS:
            raise ValueError(
                f"verdict must be one of {_APPROVAL_VERDICTS}, got {self.verdict!r}"
            )
