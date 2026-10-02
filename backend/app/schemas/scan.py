"""Request and response models for the ShadowScan API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ScanSourceKind, Severity
from app.schemas.common import PaginationMeta


class ScanUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048, examples=["https://example.com/article"])


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_location: str
    source_label: str
    category: str
    category_label: str
    matched_rule: str
    rule_description: str
    locator: str | None
    # Raw text from a hostile page. Clients must render it as text, never markup.
    evidence_text: str
    risk_weight: int
    impact: str | None
    remediation: str | None


class SeverityInfo(BaseModel):
    level: Severity
    label: str
    meaning: str
    recommended_action: str


class ScanSummary(BaseModel):
    id: uuid.UUID
    source_kind: ScanSourceKind
    target_url: str | None
    target_filename: str | None
    score: int = Field(ge=0, le=100)
    severity: SeverityInfo
    finding_count: int
    created_at: datetime


class ScanResultOut(ScanSummary):
    findings: list[FindingOut]
    extraction_summary: dict | None
    limitations: list[str]


class ScanPage(BaseModel):
    items: list[ScanSummary]
    pagination: PaginationMeta


class DemoPageOut(BaseModel):
    id: str
    title: str
    technique: str
    description: str
    expected_findings: int
    expected_severity: Severity


class ScanReportRequest(BaseModel):
    scan_id: uuid.UUID
    format: Literal["html", "pdf"] = "html"
