"""Persistence and presentation for ShadowScan results."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Finding, ScanResult, ScanSourceKind, Severity
from app.schemas.common import PaginationMeta
from app.schemas.scan import FindingOut, ScanPage, ScanResultOut, ScanSummary, SeverityInfo
from app.services.scanner.pipeline import ScanOutcome
from app.services.scanner.rules import Category, get_rules
from app.services.scanner.scoring import SEVERITY_GUIDANCE, contribution
from app.services.scanner.sources import SOURCE_INFO, SourceLocation

# Always shown with results (blueprint 13.2: "Limitations notice: always shown").
LIMITATIONS = [
    "Detection is rule-based. Paraphrased, novel, or non-English injections can go unnoticed.",
    "Only the static HTML is analysed. "
    "Content added by JavaScript after the page loads is not seen.",
    "Encoded or obfuscated payloads, such as Base64, are not decoded in this release.",
    "A clean result does not certify a page as safe. It means no configured rule matched.",
]


@dataclass(frozen=True)
class ScanFilters:
    severity: Severity | None = None
    min_score: int | None = None
    max_score: int | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


async def save_scan(
    db: AsyncSession,
    outcome: ScanOutcome,
    *,
    source_kind: ScanSourceKind,
    target_url: str | None = None,
    target_filename: str | None = None,
) -> ScanResult:
    """Store the outcome. The scanned document itself is never stored."""
    rules = get_rules()
    scan = ScanResult(
        source_kind=source_kind,
        target_url=target_url,
        target_filename=target_filename,
        score=outcome.score,
        severity=outcome.severity,
        finding_count=len(outcome.detections),
        extraction_summary=outcome.extraction_summary,
    )
    scan.findings = [
        Finding(
            source_location=d.segment.source.value,
            category=d.category.value,
            matched_rule=d.rule.id,
            locator=d.segment.locator,
            evidence_text=d.evidence,
            risk_weight=round(contribution(d)),
            impact=rules.categories[d.category].impact,
            remediation=rules.categories[d.category].remediation,
        )
        for d in sorted(outcome.detections, key=contribution, reverse=True)
    ]
    db.add(scan)
    await db.flush()
    return scan


async def get_scan(db: AsyncSession, scan_id: uuid.UUID) -> ScanResult | None:
    return await db.scalar(
        select(ScanResult)
        .where(ScanResult.id == scan_id)
        .options(selectinload(ScanResult.findings))
    )


async def list_scans(
    db: AsyncSession, filters: ScanFilters, *, limit: int, offset: int
) -> tuple[list[ScanResult], int]:
    conditions = []
    if filters.severity is not None:
        conditions.append(ScanResult.severity == filters.severity)
    if filters.min_score is not None:
        conditions.append(ScanResult.score >= filters.min_score)
    if filters.max_score is not None:
        conditions.append(ScanResult.score <= filters.max_score)
    if filters.created_from is not None:
        conditions.append(ScanResult.created_at >= filters.created_from)
    if filters.created_to is not None:
        conditions.append(ScanResult.created_at <= filters.created_to)

    total = await db.scalar(select(func.count()).select_from(ScanResult).where(*conditions))
    rows = await db.scalars(
        select(ScanResult)
        .where(*conditions)
        .order_by(ScanResult.created_at.desc(), ScanResult.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #


def severity_info(severity: Severity) -> SeverityInfo:
    guidance = SEVERITY_GUIDANCE[severity]
    return SeverityInfo(
        level=severity,
        label=guidance.label,
        meaning=guidance.meaning,
        recommended_action=guidance.action,
    )


def _source_label(value: str) -> str:
    try:
        return SOURCE_INFO[SourceLocation(value)].label
    except ValueError:
        return value


def _category_label(value: str) -> str:
    try:
        return get_rules().categories[Category(value)].label
    except ValueError:
        return value


def _rule_description(rule_id: str) -> str:
    for rule in get_rules().rules:
        if rule.id == rule_id:
            return rule.description
    return rule_id


def finding_out(finding: Finding) -> FindingOut:
    return FindingOut(
        id=finding.id,
        source_location=finding.source_location,
        source_label=_source_label(finding.source_location),
        category=finding.category,
        category_label=_category_label(finding.category),
        matched_rule=finding.matched_rule,
        rule_description=_rule_description(finding.matched_rule),
        locator=finding.locator,
        evidence_text=finding.evidence_text,
        risk_weight=finding.risk_weight,
        impact=finding.impact,
        remediation=finding.remediation,
    )


def summary_out(scan: ScanResult) -> ScanSummary:
    return ScanSummary(
        id=scan.id,
        source_kind=scan.source_kind,
        target_url=scan.target_url,
        target_filename=scan.target_filename,
        score=scan.score,
        severity=severity_info(scan.severity),
        finding_count=scan.finding_count,
        created_at=scan.created_at,
    )


def result_out(scan: ScanResult) -> ScanResultOut:
    findings = sorted(scan.findings, key=lambda f: f.risk_weight, reverse=True)
    return ScanResultOut(
        **summary_out(scan).model_dump(),
        findings=[finding_out(f) for f in findings],
        extraction_summary=scan.extraction_summary,
        limitations=LIMITATIONS,
    )


def page_out(items: list[ScanResult], total: int, limit: int, offset: int) -> ScanPage:
    return ScanPage(
        items=[summary_out(s) for s in items],
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )
