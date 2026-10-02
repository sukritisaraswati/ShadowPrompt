"""Persistence and presentation for Lab sessions and campaigns."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Campaign,
    CampaignStatus,
    PayloadPack,
    Session,
    TestResult,
    Verdict,
)
from app.schemas.common import PaginationMeta
from app.schemas.lab import (
    CampaignOut,
    CampaignPage,
    CampaignSummaryOut,
    GuidanceOut,
    LanguagePackSummary,
    LevelScoreOut,
    LevelSummary,
    PackTestOut,
    PayloadLibrarySummary,
    PayloadPackOut,
    PayloadPackSummary,
    RatingOut,
    SessionOut,
    TestResultOut,
    TopFixOut,
    TrackScoreOut,
    TrackSummary,
)
from app.services.lab.custom_packs import CustomPack, build_payloads
from app.services.lab.guidance import guidance_for, top_fixes
from app.services.lab.payloads import (
    AVAILABLE_LEVELS,
    LEVEL_CODES,
    LEVELS,
    TRACK_NAMES,
    Payload,
    PayloadLibrary,
    PayloadSpec,
    level_code,
)
from app.services.lab.scoring import RATINGS, LevelScore, overall_score, rating_for
from app.services.languages import language_name


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


def _level_scores(campaign: Campaign) -> list[LevelScore]:
    return [
        LevelScore(**{**ls, "track": ls.get("track", "direct")})
        for ls in (campaign.level_scores or [])
    ]


def track_scores_out(campaign: Campaign) -> list[TrackScoreOut]:
    scores = _level_scores(campaign)
    out = []
    for track, name in TRACK_NAMES.items():
        if any(ls.track == track.value for ls in scores):
            score = overall_score(scores, track.value)
            out.append(
                TrackScoreOut(track=track.value, name=name, score=score, rating=rating_out(score))
            )
    return out


def summary_out(campaign: Campaign, completed: int) -> CampaignSummaryOut:
    return CampaignSummaryOut(
        id=campaign.id,
        session=_session_out(campaign.session),
        levels_run=[str(code) for code in (campaign.levels_run or [])],
        status=campaign.status,
        total_tests=campaign.total_tests,
        completed_tests=completed,
        overall_score=campaign.overall_score,
        rating=rating_out(campaign.overall_score),
        track_scores=track_scores_out(campaign),
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
    )


def result_out(result: TestResult, payload: Payload | None) -> TestResultOut:
    """A stored result, described by the payload it ran (None if unknown)."""
    spec = payload.spec if payload else None
    return TestResultOut(
        id=result.id,
        payload_id=result.payload_id,
        track=result.track,
        code=level_code(result.track, result.level),
        level=result.level,
        category=result.category,
        technique=spec.technique if spec else "unknown",
        name=spec.name if spec else result.payload_id,
        description=spec.description if spec else "",
        objective=spec.objective.value if spec else "unknown",
        language=spec.language if spec else "en",
        language_name=language_name(spec.language) if spec else "English",
        custom_pack=payload.pack_name if payload else None,
        attack_text=payload.attack_text() if payload else "",
        verdict=result.verdict,
        response_summary=result.response_summary,
        evaluation_detail=result.evaluation_detail,
        latency_ms=result.latency_ms,
        created_at=result.created_at,
        guidance=GuidanceOut(**guidance_for(payload).as_dict())
        if payload is not None and result.verdict in (Verdict.FAIL, Verdict.PARTIAL)
        else None,
    )


def custom_snapshot(payloads: list[Payload]) -> list[dict]:
    """What a campaign keeps of the custom tests it ran.

    Stored with the campaign, so its results stay readable after the pack
    is deleted or replaced.
    """
    return [
        {
            "pack_name": p.pack_name,
            "spec": p.spec.model_dump(mode="json"),
            "page_html": p.page_html,
        }
        for p in payloads
        if p.pack_name is not None
    ]


def payload_resolver(
    campaign: Campaign, library: PayloadLibrary
) -> Callable[[str], Payload | None]:
    """Look up the payload behind a result: the library, or the campaign's custom tests."""
    custom: dict[str, Payload] = {}
    for item in (campaign.config or {}).get("custom_payloads", []):
        spec = PayloadSpec.model_validate(item["spec"])
        custom[spec.id] = Payload(spec, item.get("page_html"), pack_name=item.get("pack_name"))

    def resolve(payload_id: str) -> Payload | None:
        return custom.get(payload_id) or library.by_id(payload_id)

    return resolve


def _as_sent(result: TestResult, payload: Payload | None) -> Payload | None:
    """The payload as it was sent: with its hosted link, if the page was hosted."""
    hosted = (result.evaluation_detail or {}).get("hosted_page") or {}
    if payload is None or not hosted.get("url"):
        return payload
    return replace(payload, page_link=hosted["url"])


def campaign_out(campaign: Campaign, library: PayloadLibrary) -> CampaignOut:
    results = sorted(campaign.test_results, key=lambda r: (r.created_at, r.payload_id))
    resolve = payload_resolver(campaign, library)
    failed = [
        payload
        for r in results
        if r.verdict in (Verdict.FAIL, Verdict.PARTIAL)
        and (payload := resolve(r.payload_id)) is not None
    ]
    level_scores = []
    for ls in _level_scores(campaign):
        code = level_code(ls.track, ls.level)
        level_scores.append(LevelScoreOut(code=code, name=LEVELS[code].name, **ls.as_dict()))
    current_level = None
    if campaign.status in (
        CampaignStatus.PENDING,
        CampaignStatus.RUNNING,
        CampaignStatus.PAUSED,
    ):
        if results:
            current_level = level_code(results[-1].track, results[-1].level)
        elif campaign.levels_run:
            current_level = str(campaign.levels_run[0])
    return CampaignOut(
        **summary_out(campaign, len(results)).model_dump(),
        # The custom-test snapshot is internal; results already describe it.
        config={k: v for k, v in (campaign.config or {}).items() if k != "custom_payloads"}
        if campaign.config is not None
        else None,
        error_message=campaign.error_message,
        current_level=current_level,
        level_scores=level_scores,
        top_fixes=[TopFixOut(**fix) for fix in top_fixes(failed)],
        results=[result_out(r, _as_sent(r, resolve(r.payload_id))) for r in results],
    )


def page_out(
    campaigns: list[Campaign], counts: dict[uuid.UUID, int], total: int, limit: int, offset: int
) -> CampaignPage:
    return CampaignPage(
        items=[summary_out(c, counts.get(c.id, 0)) for c in campaigns],
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


def library_summary(library: PayloadLibrary) -> PayloadLibrarySummary:
    levels = [
        LevelSummary(
            code=code,
            track=info.track.value,
            level=info.level,
            name=info.name,
            description=info.description,
            category=info.category,
            danger=info.danger,
            test_count=len(library.for_level(code)),
            available=code in AVAILABLE_LEVELS,
        )
        for code, info in LEVELS.items()
    ]
    tracks = [
        TrackSummary(
            track=track.value,
            name=name,
            test_count=sum(level.test_count for level in levels if level.track == track.value),
        )
        for track, name in TRACK_NAMES.items()
    ]
    packs = [
        LanguagePackSummary(
            code=code,
            name=language_name(code),
            test_count=len(tests),
            level_counts={
                code: sum(1 for p in tests if p.code == code)
                for code in LEVEL_CODES
                if any(p.code == code for p in tests)
            },
        )
        for code, tests in library.languages().items()
    ]
    return PayloadLibrarySummary(
        version=library.version,
        total_tests=sum(level.test_count for level in levels),
        tracks=tracks,
        levels=levels,
        languages=packs,
    )


# --------------------------------------------------------------------------- #
# Custom payload packs
# --------------------------------------------------------------------------- #


async def count_packs(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(PayloadPack)) or 0)


async def find_pack_by_hash(db: AsyncSession, sha256: str) -> PayloadPack | None:
    return await db.scalar(select(PayloadPack).where(PayloadPack.sha256 == sha256))


async def create_pack(db: AsyncSession, pack: CustomPack, sha256: str) -> PayloadPack:
    counts: dict[str, int] = {}
    for payload in build_payloads(uuid.UUID(int=0), pack, pack.name):
        counts[payload.code] = counts.get(payload.code, 0) + 1
    row = PayloadPack(
        name=pack.name,
        description=pack.description or None,
        test_count=len(pack.tests),
        level_counts={code: counts[code] for code in LEVEL_CODES if code in counts},
        content=pack.model_dump(mode="json"),
        sha256=sha256,
    )
    db.add(row)
    await db.flush()
    return row


async def list_packs(db: AsyncSession) -> list[PayloadPack]:
    rows = await db.scalars(select(PayloadPack).order_by(PayloadPack.created_at.desc()))
    return list(rows)


def pack_payloads(row: PayloadPack) -> list[Payload]:
    """The pack's tests, re-validated from storage."""
    pack = CustomPack.model_validate(row.content)
    return build_payloads(row.id, pack, row.name)


def pack_summary(row: PayloadPack) -> PayloadPackSummary:
    return PayloadPackSummary(
        id=row.id,
        name=row.name,
        description=row.description,
        test_count=row.test_count,
        level_counts=dict(row.level_counts),
        created_at=row.created_at,
    )


def pack_out(row: PayloadPack) -> PayloadPackOut:
    tests = [
        PackTestOut(
            id=p.id,
            code=p.code,
            track=p.track.value,
            level=p.level,
            name=p.spec.name,
            objective=p.spec.objective.value,
            language=p.language,
        )
        for p in pack_payloads(row)
    ]
    return PayloadPackOut(**pack_summary(row).model_dump(), tests=tests)
