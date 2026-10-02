"""ShadowPrompt Lab route group -- ``/api/v1/lab`` (blueprint section 9.1).

Credentials: the API key arrives in the body of a connection test or a
campaign launch, lives in memory for that request or that campaign's run, and
is never persisted or echoed back.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.limits import campaign_rate_limit, connect_rate_limit
from app.db.models import Campaign, CampaignStatus, ReportType, Session
from app.db.session import get_db
from app.schemas.common import ErrorCode, ErrorResponse
from app.schemas.lab import (
    CampaignCreate,
    CampaignOut,
    CampaignPage,
    CampaignReportRequest,
    CampaignStarted,
    ConnectionIn,
    ConnectionTestOut,
    PayloadLibrarySummary,
)
from app.services.lab import campaign_service
from app.services.lab.evaluator import summarize
from app.services.lab.events import events
from app.services.lab.judge import Judge, get_judge
from app.services.lab.llm_client import ChatMessage, LlmBackend, LlmConfig, chat
from app.services.lab.orchestrator import ACTIVE_STATUSES, registry, run_campaign
from app.services.lab.payloads import AVAILABLE_LEVELS, get_library
from app.services.reports.campaign_report import render_campaign_report
from app.services.reports.delivery import deliver_report

router = APIRouter(prefix="/lab", tags=["lab"])

PROBE = [ChatMessage("user", "Hello, please respond with 'OK'.")]
_ERRORS = {code: {"model": ErrorResponse} for code in (400, 404, 409, 422, 429, 502, 504)}


def get_llm_backend() -> LlmBackend:
    """Transport for model calls. Overridden in tests with a mock transport."""
    return LlmBackend()


def get_lab_judge() -> Judge:
    """The Layer 3 judge. Overridden in tests with a fake sender."""
    return get_judge()


def _config(connection: ConnectionIn, *, timeout: float, retries: int) -> LlmConfig:
    return LlmConfig(
        provider=connection.provider,
        base_url=connection.base_url,
        model=connection.model,
        api_key=connection.api_key,
        timeout_seconds=timeout,
        max_retries=retries,
    )


def _not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "Campaign not found.", status_code=404)


@router.post(
    "/connect/test",
    response_model=ConnectionTestOut,
    responses=_ERRORS,
    summary="Test LLM connection",
    dependencies=[Depends(connect_rate_limit)],
)
async def test_connection(
    body: ConnectionIn,
    db: AsyncSession = Depends(get_db),
    backend: LlmBackend = Depends(get_llm_backend),
) -> ConnectionTestOut:
    """Send one benign probe. No attack payload is sent until this succeeds."""
    settings = get_settings()
    config = _config(body, timeout=min(30.0, settings.llm_timeout_seconds), retries=0)
    reply = await chat(config, PROBE, settings=settings, backend=backend)
    host = urlsplit(body.base_url).hostname or ""
    session = await campaign_service.create_session(
        db, provider=body.provider.value, model_name=body.model, endpoint_host=host
    )
    return ConnectionTestOut(
        session_id=session.id,
        provider=body.provider,
        model_name=body.model,
        endpoint_host=host,
        latency_ms=reply.latency_ms,
        reply_preview=summarize(reply.text)[:200],
    )


@router.post(
    "/campaigns",
    response_model=CampaignStarted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    summary="Start a new test campaign",
    dependencies=[Depends(campaign_rate_limit)],
)
async def start_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    backend: LlmBackend = Depends(get_llm_backend),
    judge: Judge = Depends(get_lab_judge),
) -> CampaignStarted:
    settings = get_settings()

    unavailable = sorted(set(body.levels) - AVAILABLE_LEVELS)
    if unavailable:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Some selected levels are not available.",
            status_code=422,
            detail=f"Unavailable levels: {unavailable}",
        )

    session = await db.get(Session, body.session_id)
    if session is None:
        raise AppError(
            ErrorCode.NOT_FOUND,
            "Connection session not found. Test the connection again.",
            status_code=404,
        )
    if (session.provider, session.model_name) != (
        body.connection.provider.value,
        body.connection.model,
    ):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "The connection does not match the one that was tested. Test the connection again.",
            status_code=422,
        )

    if registry.active_count() >= settings.max_concurrent_campaigns:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "Too many campaigns are running. Try again when one finishes.",
            status_code=429,
        )

    campaign_id = uuid.uuid4()
    payloads = get_library().select(body.levels, body.sample_size, seed=str(campaign_id))
    campaign = Campaign(
        id=campaign_id,
        session_id=session.id,
        levels_run=body.levels,
        status=CampaignStatus.PENDING,
        total_tests=len(payloads),
        config={
            "sample_size": body.sample_size,
            "timeout_seconds": body.timeout_seconds,
            "max_retries": body.max_retries,
        },
    )
    db.add(campaign)
    # Commit before the run starts, so the background task sees the row.
    await db.commit()

    config = _config(body.connection, timeout=body.timeout_seconds, retries=body.max_retries)
    registry.start(
        campaign_id,
        lambda control: run_campaign(
            campaign_id,
            config,
            payloads,
            control,
            settings=settings,
            backend=backend,
            judge=judge,
        ),
    )
    return CampaignStarted(
        campaign_id=campaign_id, status=CampaignStatus.PENDING, total_tests=len(payloads)
    )


SSE_HEARTBEAT_SECONDS = 15.0


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


@router.get(
    "/campaigns/{campaign_id}/stream",
    responses={**_ERRORS, 200: {"content": {"text/event-stream": {}}}},
    summary="Stream live test results",
)
async def stream_campaign(
    campaign_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Server-Sent Events: a snapshot, then one event per verdict and status change.

    The first event is the full campaign as it stands, so a client that joins
    late or reconnects is immediately up to date. The stream ends with a
    ``done`` event when the campaign finishes.
    """
    campaign = await campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise _not_found()
    snapshot = campaign_service.campaign_out(campaign, get_library()).model_dump(mode="json")
    finished = campaign.status not in ACTIVE_STATUSES
    queue = None if finished else events.subscribe(campaign_id)

    async def stream() -> AsyncIterator[str]:
        try:
            yield "retry: 3000\n\n"
            yield _sse({"type": "snapshot", "campaign": snapshot})
            if queue is None:
                yield _sse({"type": "done", "status": snapshot["status"]})
                return
            # The run may have finished between the snapshot and subscribing.
            if not registry.is_running(campaign_id):
                yield _sse({"type": "resync"})
                return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), SSE_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event)
                if event["type"] in ("done", "resync"):
                    return
        finally:
            if queue is not None:
                events.unsubscribe(campaign_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/campaigns/{campaign_id}",
    response_model=CampaignOut,
    responses=_ERRORS,
    summary="Get full campaign result",
)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CampaignOut:
    campaign = await campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise _not_found()
    return campaign_service.campaign_out(campaign, get_library())


@router.get(
    "/campaigns",
    response_model=CampaignPage,
    responses=_ERRORS,
    summary="List past campaigns",
)
async def list_campaigns(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    model_name: str | None = Query(None, max_length=200),
    status_filter: CampaignStatus | None = Query(None, alias="status"),
    min_score: float | None = Query(None, ge=0, le=100),
    max_score: float | None = Query(None, ge=0, le=100),
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> CampaignPage:
    filters = campaign_service.CampaignFilters(
        model_name=model_name,
        status=status_filter,
        min_score=min_score,
        max_score=max_score,
        started_from=started_from,
        started_to=started_to,
    )
    items, total = await campaign_service.list_campaigns(db, filters, limit=limit, offset=offset)
    counts = await campaign_service.count_results(db, [c.id for c in items])
    return campaign_service.page_out(items, counts, total, limit, offset)


@router.post(
    "/campaigns/{campaign_id}/stop",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    summary="Stop a running campaign",
)
async def stop_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Finishes the test in progress, saves results so far, then stops."""
    if registry.request_stop(campaign_id):
        return {"campaign_id": str(campaign_id), "status": "stopping"}
    if await db.get(Campaign, campaign_id) is None:
        raise _not_found()
    raise AppError(ErrorCode.CONFLICT, "This campaign is not running.", status_code=409)


@router.post(
    "/campaigns/{campaign_id}/pause",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    summary="Pause a running campaign",
)
async def pause_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Finishes the test in progress, then waits until resumed or stopped."""
    if registry.pause(campaign_id):
        return {"campaign_id": str(campaign_id), "status": "pausing"}
    if await db.get(Campaign, campaign_id) is None:
        raise _not_found()
    raise AppError(ErrorCode.CONFLICT, "This campaign is not running.", status_code=409)


@router.post(
    "/campaigns/{campaign_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    summary="Resume a paused campaign",
)
async def resume_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    if registry.resume(campaign_id):
        return {"campaign_id": str(campaign_id), "status": "resuming"}
    if await db.get(Campaign, campaign_id) is None:
        raise _not_found()
    raise AppError(ErrorCode.CONFLICT, "This campaign is not running.", status_code=409)


@router.delete(
    "/campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    summary="Delete a campaign record",
)
async def delete_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    if registry.is_running(campaign_id):
        raise AppError(ErrorCode.CONFLICT, "Stop the campaign before deleting it.", status_code=409)
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise _not_found()
    await db.delete(campaign)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reports",
    responses={
        **_ERRORS,
        200: {
            "content": {"text/html": {}, "application/pdf": {}},
            "description": "HTML or PDF report",
        },
    },
    summary="Generate downloadable report",
)
async def generate_campaign_report(
    body: CampaignReportRequest, db: AsyncSession = Depends(get_db)
) -> Response:
    campaign = await campaign_service.get_campaign(db, body.campaign_id)
    if campaign is None:
        raise _not_found()
    if campaign.status in ACTIVE_STATUSES:
        raise AppError(ErrorCode.CONFLICT, "The campaign is still running.", status_code=409)
    html = render_campaign_report(campaign_service.campaign_out(campaign, get_library()))
    return await deliver_report(
        db,
        report_type=ReportType.LAB_CAMPAIGN,
        reference_id=campaign.id,
        html=html,
        fmt=body.format,
        stem="campaign",
    )


@router.get(
    "/payload-library/summary",
    response_model=PayloadLibrarySummary,
    summary="Get payload library metadata",
)
async def payload_library_summary() -> PayloadLibrarySummary:
    """Level names and test counts only -- never the payload text itself."""
    return campaign_service.library_summary(get_library())
