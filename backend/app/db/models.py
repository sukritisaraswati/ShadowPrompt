"""ORM models -- the data model from blueprint section 11.

Deliberate omissions, which are security requirements rather than oversights:

* No table stores an LLM API key, in any form. Keys live in request-scoped
  memory only.
* ``test_results`` stores a *summary* of the model response, never the full
  raw text.
* ``scan_results`` stores metadata and findings only. Raw fetched HTML is
  discarded once extraction completes.

Evidence text is stored as the raw extracted string and escaped at every
output boundary instead: React renders it as text, and report templates
autoescape it. Storing it pre-escaped would double-escape in the UI and invite
someone to "fix" that with raw HTML rendering, which is the real XSS risk.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class Verdict(enum.StrEnum):
    """Outcome of a single attack test case (blueprint 5.2)."""

    PASS = "PASS"  # noqa: S105 - a verdict, not a credential
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    UNCLEAR = "UNCLEAR"


class CampaignStatus(enum.StrEnum):
    """Lifecycle of a Lab campaign."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class Severity(enum.StrEnum):
    """ShadowScan risk bands (blueprint 6.3)."""

    CLEAN = "clean"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScanSourceKind(enum.StrEnum):
    """Where the scanned document came from."""

    URL = "url"
    UPLOAD = "upload"
    DEMO = "demo"


class ReportType(enum.StrEnum):
    LAB_CAMPAIGN = "lab_campaign"
    SHADOWSCAN = "shadowscan"


class ReportFormat(enum.StrEnum):
    HTML = "html"
    PDF = "pdf"


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Portable enum column.

    ``native_enum=False`` stores the value as VARCHAR plus a CHECK constraint,
    which behaves identically on PostgreSQL and on the SQLite dev fallback.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
        length=32,
    )


# --------------------------------------------------------------------------- #
# Lab tables
# --------------------------------------------------------------------------- #


class Session(Base):
    """One Lab session. Records which model was tested -- never the key."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    # Host name of the endpoint, for display. Never the full URL or the key.
    endpoint_host: Mapped[str | None] = mapped_column(String(255))

    campaigns: Mapped[list[Campaign]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Campaign(Base):
    """One attack campaign run against a connected model."""

    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Which of levels 1-5 were selected for this run, e.g. [1, 2, 3].
    # Level codes run, e.g. ["D1", "D2", "I1"].
    levels_run: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_tests: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Run settings such as sample size, timeout and retries. Never credentials.
    config: Mapped[dict | None] = mapped_column(JSON)
    # Per-level pass, partial, fail and unclear counts with each level's score.
    level_scores: Mapped[list | None] = mapped_column(JSON)
    # Why a campaign ended early, in plain language. Never provider raw output.
    error_message: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[CampaignStatus] = mapped_column(
        _enum(CampaignStatus, "campaign_status"),
        nullable=False,
        default=CampaignStatus.PENDING,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[Session] = relationship(back_populates="campaigns")
    test_results: Mapped[list[TestResult]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class TestResult(Base):
    """One test case result within a campaign."""

    __tablename__ = "test_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "direct" or "indirect"; with ``level`` it gives the level code, e.g. D3.
    track: Mapped[str] = mapped_column(
        String(16), nullable=False, default="direct", server_default="direct"
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    # References an entry in the JSON payload library, which is never exposed
    # to users in full.
    payload_id: Mapped[str] = mapped_column(String(128), nullable=False)
    verdict: Mapped[Verdict] = mapped_column(_enum(Verdict, "verdict"), nullable=False)
    # A truncated, safe summary -- NOT the full raw response from the model.
    response_summary: Mapped[str | None] = mapped_column(Text)
    # Which evaluation layer decided, and why.
    evaluation_detail: Mapped[dict | None] = mapped_column(JSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    campaign: Mapped[Campaign] = relationship(back_populates="test_results")

    __table_args__ = (Index("ix_test_results_campaign_level", "campaign_id", "level"),)


class HostedPage(Base):
    """An indirect test's attack page, served at a link for a chatbot to fetch."""

    __tablename__ = "hosted_pages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Unguessable; the page is reachable only through its link.
    link_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload_id: Mapped[str] = mapped_column(String(128), nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_user_agent: Mapped[str | None] = mapped_column(String(200))


class PayloadPack(Base):
    """A custom test pack uploaded by a user, validated before it is stored."""

    __tablename__ = "payload_packs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    test_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Number of tests at each level, e.g. {"1": 3, "4": 1}.
    level_counts: Mapped[dict] = mapped_column(JSON, nullable=False)
    # The validated pack, re-validated whenever it is used.
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    # SHA-256 of the canonical content, so the same file is stored once.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# --------------------------------------------------------------------------- #
# ShadowScan tables
# --------------------------------------------------------------------------- #


class ScanResult(Base):
    """One ShadowScan run against a URL or an uploaded file."""

    __tablename__ = "scan_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_kind: Mapped[ScanSourceKind] = mapped_column(
        _enum(ScanSourceKind, "scan_source_kind"),
        nullable=False,
        default=ScanSourceKind.URL,
        server_default=ScanSourceKind.URL.value,
    )
    # Exactly one of these is set, depending on the scan source.
    target_url: Mapped[str | None] = mapped_column(String(2048))
    target_filename: Mapped[str | None] = mapped_column(String(512))
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    severity: Mapped[Severity] = mapped_column(
        _enum(Severity, "severity"),
        nullable=False,
        default=Severity.CLEAN,
        index=True,
    )
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Segment counts per source location, plus whether limits truncated the scan.
    extraction_summary: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    findings: Mapped[list[Finding]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class Finding(Base):
    """One detection within a scan."""

    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scan_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Where in the document it was found, e.g. "html_comment", "meta_tag".
    source_location: Mapped[str] = mapped_column(String(64), nullable=False)
    # One of the seven detection categories, e.g. "instruction_override".
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="unknown", server_default="unknown"
    )
    # Which detection rule matched, e.g. "instruction_override.ignore_previous".
    matched_rule: Mapped[str] = mapped_column(String(128), nullable=False)
    # Short description of the element, e.g. "<img> alt" or "comment #2".
    locator: Mapped[str | None] = mapped_column(String(256))
    # Raw extracted text, escaped at output. Rendered as plain text only.
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    # How the matched text was recovered, e.g. "base64" or "split"; null when
    # it matched exactly as written on the page. Evidence is the decoded text.
    obfuscation: Mapped[str | None] = mapped_column(String(64))
    risk_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impact: Mapped[str | None] = mapped_column(Text)
    remediation: Mapped[str | None] = mapped_column(Text)

    scan: Mapped[ScanResult] = relationship(back_populates="findings")

    __table_args__ = (Index("ix_findings_scan_rule", "scan_id", "matched_rule"),)


# --------------------------------------------------------------------------- #
# Shared
# --------------------------------------------------------------------------- #


class Report(Base):
    """Metadata for a generated report file. The file itself lives on disk."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[ReportType] = mapped_column(_enum(ReportType, "report_type"), nullable=False)
    # Campaign id or scan id, depending on ``type``. Not a DB-level foreign key
    # because it points at one of two tables.
    reference_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    format: Mapped[ReportFormat] = mapped_column(
        _enum(ReportFormat, "report_format"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
