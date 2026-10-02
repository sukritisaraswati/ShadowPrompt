"""Shared response schemas.

Every error the API returns uses the same envelope so the frontend can render a
specific message per failure mode -- the blueprint requires distinguishable
errors for wrong key, wrong URL, model not found, rate limited, and blocked
SSRF target.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    """Stable, machine-readable error identifiers."""

    # Generic
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    CONFLICT = "CONFLICT"

    # ShadowScan
    BLOCKED_TARGET = "BLOCKED_TARGET"
    FETCH_FAILED = "FETCH_FAILED"
    FETCH_TIMEOUT = "FETCH_TIMEOUT"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"

    # Lab
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    LLM_UNREACHABLE = "LLM_UNREACHABLE"
    LLM_MODEL_NOT_FOUND = "LLM_MODEL_NOT_FOUND"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_TIMEOUT = "LLM_TIMEOUT"


class ErrorResponse(BaseModel):
    """Uniform error body. Never contains credentials or raw hostile content."""

    code: ErrorCode
    message: str
    detail: str | None = None


class ServiceStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class HealthResponse(BaseModel):
    """Response for ``GET /health`` (blueprint section 9.2)."""

    status: ServiceStatus
    version: str
    environment: str
    uptime_seconds: float
    database: ServiceStatus
    timestamp: datetime


class PaginationMeta(BaseModel):
    """Pagination envelope shared by every history listing."""

    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class Page(BaseModel):
    """A page of results plus its pagination metadata."""

    items: list[Any]
    pagination: PaginationMeta
