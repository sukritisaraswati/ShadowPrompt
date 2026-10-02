"""Persistence and presentation for Lab sessions and campaigns."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Campaign, CampaignStatus, Session, TestResult
from app.schemas.common import PaginationMeta
from app.schemas.lab import (
    CampaignOut,
    CampaignPage,
    CampaignSummaryOut,
    LevelScoreOut,
    LevelSummary,
    PayloadLibrarySummary,
    RatingOut,
    SessionOut,
    TestResultOut,
)
from app.services.lab.payloads import AVAILABLE_LEVELS, LEVEL_INFO, PayloadLibrary
from app.services.lab.scoring import RATINGS, rating_for


@dataclass(frozen=True)
class CampaignFilters:
    model_name: str | None = None
    status: CampaignStatus | None = None
    min_score: float | None = None
    max_score: float | None = None
    started_from: datetime | None = None
    started_to: datetime | None = None


async def create_session(
    db: AsyncSession, *, provider: str, model_name: str, endpoint_host: str
) -> Session:
    session = Session(provider=provider, model_name=model_name, endpoint_host=endpoint_host)
    db.add(session)
    await db.flush()
    return session


async def get_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> Campaign | None:
    return await db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.session), selectinload(Campaign.test_results))
        .execution_options(populate_existing=True)
    )


async def count_results(db: AsyncSession, campaign_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not campaign_ids:
        return {}
    rows = await db.execute(
        select(TestResult.campaign_id, func.count())
        .where(TestResult.campaign_id.in_(campaign_ids))
        .group_by(TestResult.campaign_id)
    )
    return {campaign_id: count for campaign_id, count in rows.all()}


async def list_campaigns(
    db: AsyncSession, filters: CampaignFilters, *, limit: int, offset: int
) -> tuple[list[Campaign], int]:
    conditions = []
    if filters.model_name:
        conditions.append(Session.model_name.ilike(f"%{filters.model_name}%"))
    if filters.status is not None:
        conditions.append(Campaign.status == filters.status)
    if filters.min_score is not None:
        conditions.append(Campaign.overall_score >= filters.min_score)
    if filters.max_score is not None:
        conditions.append(Campaign.overall_score <= filters.max_score)
    if filters.started_from is not None:
        conditions.append(Campaign.started_at >= filters.started_from)
    if filters.started_to is not None:
        conditions.append(Campaign.started_at <= filters.started_to)

    base = select(Campaign).join(Session).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.scalars(
        base.options(selectinload(Campaign.session))
        .order_by(Campaign.started_at.desc(), Campaign.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #


def rating_out(score: float | None) -> RatingOut | None:
    if score is None:
        return None
    rating = rating_for(score)
    info = RATINGS[rating]
    return RatingOut(
        level=rating,
        label=info.label,
        interpretation=info.interpretation,
        recommendation=info.recommendation,
    )


def _session_out(session: Session) -> SessionOut:
    return SessionOut(
        id=session.id,
        provider=session.provider,
        model_name=session.model_name,
        endpoint_host=session.endpoint_host,
    )


def summary_out(campaign: Campaign, completed: int) -> CampaignSummaryOut:
    return CampaignSummaryOut(
        id=campaign.id,
        session=_session_out(campaign.session),
        levels_run=list(campaign.levels_run or []),
        status=campaign.status,
        total_tests=campaign.total_tests,
        completed_tests=completed,
        overall_score=campaign.overall_score,
        rating=rating_out(campaign.overall_score),
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
    )


def result_out(result: TestResult, library: PayloadLibrary) -> TestResultOut:
    payload = library.by_id(result.payload_id)
    spec = payload.spec if payload else None
    return TestResultOut(
        id=result.id,
        payload_id=result.payload_id,
        level=result.level,
        category=result.category,
        technique=spec.technique if spec else "unknown",
        name=spec.name if spec else result.payload_id,
        description=spec.description if spec else "",
        objective=spec.objective.value if spec else "unknown",
        attack_text=payload.attack_text() if payload else "",
        verdict=result.verdict,
        response_summary=result.response_summary,
        evaluation_detail=result.evaluation_detail,
        latency_ms=result.latency_ms,
        created_at=result.created_at,
    )


def campaign_out(campaign: Campaign, library: PayloadLibrary) -> CampaignOut:
    results = sorted(campaign.test_results, key=lambda r: (r.created_at, r.payload_id))
    level_scores = [
        LevelScoreOut(name=LEVEL_INFO[ls["level"]][0], **ls) for ls in (campaign.level_scores or [])
    ]
    current_level = None
    if campaign.status in (
        CampaignStatus.PENDING,
        CampaignStatus.RUNNING,
        CampaignStatus.PAUSED,
    ):
        current_level = results[-1].level if results else min(campaign.levels_run or [1])
    return CampaignOut(
        **summary_out(campaign, len(results)).model_dump(),
        config=campaign.config,
        error_message=campaign.error_message,
        current_level=current_level,
        level_scores=level_scores,
        results=[result_out(r, library) for r in results],
    )


def page_out(
    campaigns: list[Campaign], counts: dict[uuid.UUID, int], total: int, limit: int, offset: int
) -> CampaignPage:
    return CampaignPage(
        items=[summary_out(c, counts.get(c.id, 0)) for c in campaigns],
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


def library_summary(library: PayloadLibrary) -> PayloadLibrarySummary:
    levels = []
    for level, (name, category, danger) in LEVEL_INFO.items():
        levels.append(
            LevelSummary(
                level=level,
                name=name,
                category=category,
                danger=danger,
                test_count=len(library.for_level(level)),
                available=level in AVAILABLE_LEVELS,
            )
        )
    return PayloadLibrarySummary(
        version=library.version, total_tests=len(library.payloads), levels=levels
    )
