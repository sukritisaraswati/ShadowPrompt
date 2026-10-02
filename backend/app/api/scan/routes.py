"""ShadowScan route group -- ``/api/v1/scan`` (blueprint section 9.2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.limits import scan_rate_limit
from app.db.models import ReportType, ScanSourceKind, Severity
from app.db.session import get_db
from app.schemas.common import ErrorCode, ErrorResponse
from app.schemas.scan import (
    DemoPageOut,
    ScanPage,
    ScanReportRequest,
    ScanResultOut,
    ScanUrlRequest,
)
from app.services import scan_service
from app.services.reports.delivery import deliver_report
from app.services.reports.scan_report import render_scan_report
from app.services.scanner.demo_pages import DEMO_PAGES, load_demo_content
from app.services.scanner.fetcher import fetch_page
from app.services.scanner.intake import sanitize_filename, validate_upload
from app.services.scanner.pipeline import scan_document

router = APIRouter(prefix="/scan", tags=["shadowscan"])

_ERRORS = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
}


async def _scan_and_store(
    db: AsyncSession,
    document: bytes,
    *,
    source_kind: ScanSourceKind,
    target_url: str | None = None,
    target_filename: str | None = None,
) -> ScanResultOut:
    # Parsing and regex matching are CPU-bound; keep them off the event loop.
    outcome = await run_in_threadpool(scan_document, document)
    scan = await scan_service.save_scan(
        db,
        outcome,
        source_kind=source_kind,
        target_url=target_url,
        target_filename=target_filename,
    )
    return scan_service.result_out(scan)


def _not_found(what: str) -> AppError:
    return AppError(ErrorCode.NOT_FOUND, f"{what} not found.", status_code=404)


@router.post(
    "/url",
    response_model=ScanResultOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Scan a URL",
    dependencies=[Depends(scan_rate_limit)],
)
async def scan_url(body: ScanUrlRequest, db: AsyncSession = Depends(get_db)) -> ScanResultOut:
    """Fetch a public page through the SSRF-guarded fetcher, then scan it."""
    page = await fetch_page(body.url)
    return await _scan_and_store(
        db, page.content, source_kind=ScanSourceKind.URL, target_url=page.final_url
    )


@router.post(
    "/html",
    response_model=ScanResultOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Upload and scan an HTML file",
    dependencies=[Depends(scan_rate_limit)],
)
async def scan_html_upload(
    file: UploadFile = File(..., description=".html or .htm file, 2 MB maximum"),
    db: AsyncSession = Depends(get_db),
) -> ScanResultOut:
    settings = get_settings()
    filename = sanitize_filename(file.filename)
    # Read one byte past the limit so an oversized file is detected, not truncated.
    data = await file.read(settings.upload_max_bytes + 1)
    validate_upload(filename, file.content_type, data, settings.upload_max_bytes)
    return await _scan_and_store(
        db, data, source_kind=ScanSourceKind.UPLOAD, target_filename=filename
    )


@router.get(
    "/results/{scan_id}",
    response_model=ScanResultOut,
    responses=_ERRORS,
    summary="Retrieve a past scan",
)
async def get_scan_result(scan_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ScanResultOut:
    scan = await scan_service.get_scan(db, scan_id)
    if scan is None:
        raise _not_found("Scan")
    return scan_service.result_out(scan)


@router.get(
    "/results",
    response_model=ScanPage,
    responses=_ERRORS,
    summary="List past scan history",
)
async def list_scan_results(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    severity: Severity | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    max_score: int | None = Query(None, ge=0, le=100),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> ScanPage:
    filters = scan_service.ScanFilters(
        severity=severity,
        min_score=min_score,
        max_score=max_score,
        created_from=created_from,
        created_to=created_to,
    )
    items, total = await scan_service.list_scans(db, filters, limit=limit, offset=offset)
    return scan_service.page_out(items, total, limit, offset)


@router.get("/demo-pages", response_model=list[DemoPageOut], summary="List all demo pages")
async def list_demo_pages() -> list[DemoPageOut]:
    return [
        DemoPageOut(
            id=page.id,
            title=page.title,
            technique=page.technique,
            description=page.description,
            expected_findings=page.expected_findings,
            expected_severity=page.expected_severity,
        )
        for page in DEMO_PAGES.values()
    ]


@router.post(
    "/demo-pages/{demo_id}/scan",
    response_model=ScanResultOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Scan a specific demo page",
)
async def scan_demo_page(demo_id: str, db: AsyncSession = Depends(get_db)) -> ScanResultOut:
    """Scans fixed server-side content. Ids are allowlisted, never paths."""
    content = load_demo_content(demo_id)
    if content is None:
        raise _not_found("Demo page")
    return await _scan_and_store(
        db,
        content,
        source_kind=ScanSourceKind.DEMO,
        target_filename=DEMO_PAGES[demo_id].filename,
    )


@router.post(
    "/reports",
    responses={
        **_ERRORS,
        200: {
            "content": {"text/html": {}, "application/pdf": {}},
            "description": "HTML or PDF report",
        },
    },
    summary="Generate scan report",
)
async def generate_scan_report(
    body: ScanReportRequest, db: AsyncSession = Depends(get_db)
) -> Response:
    scan = await scan_service.get_scan(db, body.scan_id)
    if scan is None:
        raise _not_found("Scan")
    return await deliver_report(
        db,
        report_type=ReportType.SHADOWSCAN,
        reference_id=scan.id,
        html=render_scan_report(scan),
        fmt=body.format,
        stem="shadowscan",
    )
