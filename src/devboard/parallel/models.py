from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Finding(BaseModel):
    file: Optional[str]
    line: Optional[int]
    category: str
    category_namespace: str
    severity: str
    body: str


class DedupedReport(BaseModel):
    findings: List[Finding] = Field(default_factory=list)
    overlap_count: int = 0


class OverallVerdict(BaseModel):
    status: str
    reasons: List[str] = Field(default_factory=list)
    note: Optional[str] = None
