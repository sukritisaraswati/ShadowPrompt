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
from app.services.lab.payloads import LEVEL_CODES
from app.services.lab.scoring import Rating
from app.services.languages import EXTRA_LANGUAGES


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
    # Level codes: D1 to D5 (direct) and I1 to I5 (indirect).
    levels: list[str] = Field(min_length=1, max_length=len(LEVEL_CODES))
    # Tests per level. ``None`` runs every test in each selected level.
    sample_size: int | None = Field(default=None, ge=1, le=40)
    timeout_seconds: float = Field(default=30.0, ge=5, le=120)
    max_retries: int = Field(default=1, ge=0, le=3)
    # Language packs to add to the English tests, e.g. ["es", "hi"].
    languages: list[str] = Field(default_factory=list, max_length=len(EXTRA_LANGUAGES))
    # Uploaded custom packs whose tests join the selected levels.
    custom_pack_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)

    @field_validator("languages")
    @classmethod
    def _valid_languages(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(EXTRA_LANGUAGES))
        if unknown:
            raise ValueError(f"unsupported languages: {unknown}")
        return [code for code in EXTRA_LANGUAGES if code in value]

    @field_validator("levels")
    @classmethod
    def _valid_levels(cls, value: list[str]) -> list[str]:
        codes = {str(code).strip().upper() for code in value}
        unknown = sorted(codes - set(LEVEL_CODES))
        if unknown:
            raise ValueError(f"unknown levels {unknown}; use D1 to D5 and I1 to I5")
        return [code for code in LEVEL_CODES if code in codes]


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
    code: str
    track: str
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
    track: str = "direct"
    code: str = ""
    level: int
    category: str
    technique: str
    name: str
    description: str
    objective: str
    language: str = "en"
    language_name: str = "English"
    # Name of the uploaded pack this test came from, if any.
    custom_pack: str | None = None
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


class TrackScoreOut(BaseModel):
    track: str
    name: str
    score: float | None
    rating: RatingOut | None


class CampaignSummaryOut(BaseModel):
    id: uuid.UUID
    session: SessionOut
    levels_run: list[str]
    status: CampaignStatus
    total_tests: int
    completed_tests: int
    overall_score: float | None
    rating: RatingOut | None
    # The score in each track that was run.
    track_scores: list[TrackScoreOut] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None


class CampaignOut(CampaignSummaryOut):
    config: dict | None
    error_message: str | None
    # The level code being run, e.g. "D2", while the campaign is active.
    current_level: str | None
    level_scores: list[LevelScoreOut]
    results: list[TestResultOut]


class CampaignPage(BaseModel):
    items: list[CampaignSummaryOut]
    pagination: PaginationMeta


class LabCapabilities(BaseModel):
    """What this deployment allows, so the interface can explain its limits."""

    # True only on self-hosted deployments with LLM_ALLOW_PRIVATE_ENDPOINTS set.
    local_endpoints_allowed: bool
    # True when the Layer 3 judge is configured and switched on.
    judge_enabled: bool


class LevelSummary(BaseModel):
    code: str
    track: str
    level: int
    name: str
    description: str
    category: str
    danger: str
    test_count: int
    available: bool


class TrackSummary(BaseModel):
    track: str
    name: str
    test_count: int


class LanguagePackSummary(BaseModel):
    code: str
    name: str
    test_count: int
    # Tests in this pack at each level, keyed by level code.
    level_counts: dict[str, int]


class PayloadLibrarySummary(BaseModel):
    version: int
    # English tests, which every campaign runs.
    total_tests: int
    tracks: list[TrackSummary] = Field(default_factory=list)
    levels: list[LevelSummary]
    # Opt-in packs in other languages.
    languages: list[LanguagePackSummary] = Field(default_factory=list)


class PackTestOut(BaseModel):
    id: str
    code: str
    track: str
    level: int
    name: str
    objective: str
    language: str


class PayloadPackSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    test_count: int
    # Tests at each level, keyed by level code.
    level_counts: dict[str, int]
    created_at: datetime


class PayloadPackOut(PayloadPackSummary):
    tests: list[PackTestOut]


class CampaignReportRequest(BaseModel):
    campaign_id: uuid.UUID
    format: Literal["html", "pdf"] = "html"
