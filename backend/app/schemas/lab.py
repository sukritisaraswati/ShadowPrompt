"""Request and response models for the ShadowPrompt Lab API.

The API key arrives as a :class:`pydantic.SecretStr`. It is masked in every
``repr``, never serialised into a response, and never written to a model
that maps to a database row.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.db.models import CampaignStatus, Verdict
from app.schemas.common import PaginationMeta
from app.services.lab.llm_client import Provider
from app.services.lab.scoring import Rating


class ConnectionIn(BaseModel):
    provider: Provider
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    api_key: SecretStr | None = Field(default=None, max_length=1000)

    @field_validator("base_url", "model")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("api_key")
    @classmethod
    def _blank_key_is_none(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None
        return SecretStr(value.get_secret_value().strip())


class ConnectionTestOut(BaseModel):
    session_id: uuid.UUID
    provider: Provider
    model_name: str
    endpoint_host: str
    latency_ms: int
    reply_preview: str


class CampaignCreate(BaseModel):
    session_id: uuid.UUID
    connection: ConnectionIn
    levels: list[int] = Field(min_length=1, max_length=5)
    # Tests per level. ``None`` runs every test in each selected level.
    sample_size: int | None = Field(default=None, ge=1, le=40)
    timeout_seconds: float = Field(default=30.0, ge=5, le=120)
    max_retries: int = Field(default=1, ge=0, le=3)

    @field_validator("levels")
    @classmethod
    def _valid_levels(cls, value: list[int]) -> list[int]:
        if any(level not in range(1, 6) for level in value):
            raise ValueError("levels must be between 1 and 5")
        return sorted(set(value))


class CampaignStarted(BaseModel):
    campaign_id: uuid.UUID
    status: CampaignStatus
    total_tests: int


class RatingOut(BaseModel):
    level: Rating
    label: str
    interpretation: str
    recommendation: str


class LevelScoreOut(BaseModel):
    level: int
    name: str
    total: int
    passed: int
    partial: int
    failed: int
    unclear: int
    score: float | None


class TestResultOut(BaseModel):
    id: uuid.UUID
    payload_id: str
    level: int
    category: str
    technique: str
    name: str
    description: str
    objective: str
    # The attack text, shown only once the test has run.
    attack_text: str
    verdict: Verdict
    # A trimmed summary of the model's reply. Untrusted text: render as text.
    response_summary: str | None
    evaluation_detail: dict | None
    latency_ms: int | None
    created_at: datetime


class SessionOut(BaseModel):
    id: uuid.UUID
    provider: str
    model_name: str
    endpoint_host: str | None


class CampaignSummaryOut(BaseModel):
    id: uuid.UUID
    session: SessionOut
    levels_run: list[int]
    status: CampaignStatus
    total_tests: int
    completed_tests: int
    overall_score: float | None
    rating: RatingOut | None
    started_at: datetime
    completed_at: datetime | None


class CampaignOut(CampaignSummaryOut):
    config: dict | None
    error_message: str | None
    current_level: int | None
    level_scores: list[LevelScoreOut]
    results: list[TestResultOut]


class CampaignPage(BaseModel):
    items: list[CampaignSummaryOut]
    pagination: PaginationMeta


class LevelSummary(BaseModel):
    level: int
    name: str
    category: str
    danger: str
    test_count: int
    available: bool


class PayloadLibrarySummary(BaseModel):
    version: int
    total_tests: int
    levels: list[LevelSummary]


class CampaignReportRequest(BaseModel):
    campaign_id: uuid.UUID
    format: Literal["html", "pdf"] = "html"
