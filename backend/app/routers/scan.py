"""
ShadowScan API Router
All /api/v1/scan/* endpoints for URL scanning, file upload, results, demo pages, and reports.
"""

import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import ScanResult, Finding
from app.config import settings
from app.scanner.pipeline import scan_html, scan_url as pipeline_scan_url, ScanOutput
from app.demo_pages.registry import get_demo_pages, get_demo_page_content, DemoPageNotFoundError
from app.reports.generator import generate_html_report


router = APIRouter()


# --- Request/Response Models ---

class UrlScanRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("URL is required")
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class FindingResponse(BaseModel):
    id: str
    source_location: str
    matched_rule: str
    matched_category: str
    evidence_text: str
    risk_weight: float
    impact: str
    remediation: str

    class Config:
        from_attributes = True


class ScanResultResponse(BaseModel):
    id: str
    target_url: Optional[str] = None
    target_filename: Optional[str] = None
    scan_type: str
    score: int
    severity: str
    finding_count: int
    created_at: str
    findings: list[FindingResponse] = []

    class Config:
        from_attributes = True


class ScanResultSummary(BaseModel):
    id: str
    target_url: Optional[str] = None
    target_filename: Optional[str] = None
    scan_type: str
    score: int
    severity: str
    finding_count: int
    created_at: str

    class Config:
        from_attributes = True


class ScanErrorResponse(BaseModel):
    error: str
    error_code: str


class ReportRequest(BaseModel):
    scan_id: str


# --- Helper Functions ---

async def _save_scan(db: AsyncSession, output: ScanOutput) -> ScanResult:
    """Persist a scan result and its findings to the database."""
    scan = ScanResult(
        target_url=output.target_url,
        target_filename=output.target_filename,
        scan_type=output.scan_type,
        score=output.score,
        severity=output.severity,
        finding_count=output.finding_count,
    )
    db.add(scan)
    await db.flush()  # Get the generated ID

    for f in output.findings:
        finding = Finding(
            scan_id=scan.id,
            source_location=f.source_location,
            matched_rule=f.matched_rule,
            matched_category=f.matched_category,
            evidence_text=f.evidence_text,
            risk_weight=f.risk_weight,
            impact=f.impact,
            remediation=f.remediation,
        )
        db.add(finding)

    await db.commit()
    await db.refresh(scan, attribute_names=["findings"])
    return scan


# --- Endpoints ---

@router.post("/url", response_model=ScanResultResponse)
async def scan_url_endpoint(request: UrlScanRequest, db: AsyncSession = Depends(get_db)):
    """
    Scan a URL for prompt injection indicators.
    Fetches the HTML content and analyzes it for suspicious patterns.
    """
    output = await pipeline_scan_url(request.url)

    if output.error:
        raise HTTPException(
            status_code=400 if output.error_code == "BLOCKED_TARGET" else 422,
            detail={"error": output.error, "error_code": output.error_code},
        )

    scan = await _save_scan(db, output)

    return _scan_to_response(scan)


@router.post("/html", response_model=ScanResultResponse)
async def scan_html_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and scan an HTML file for prompt injection indicators.
    Accepts .html and .htm files up to 2MB.
    """
    # Validate file extension
    if file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"File type '{ext}' is not supported. Only .html and .htm files are accepted.",
                    "error_code": "INVALID_FILE_TYPE",
                },
            )

    # Read and validate file size
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"File size ({len(content)} bytes) exceeds the {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB limit.",
                "error_code": "FILE_TOO_LARGE",
            },
        )

    # Decode and scan
    try:
        html_content = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            html_content = content.decode("latin-1")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Could not decode the file. Please ensure it is a valid HTML file.",
                    "error_code": "DECODE_ERROR",
                },
            )

    output = scan_html(
        html_content=html_content,
        scan_type="file",
        target_filename=file.filename,
    )

    scan = await _save_scan(db, output)

    return _scan_to_response(scan)


@router.get("/results/{scan_id}", response_model=ScanResultResponse)
async def get_scan_result(scan_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve a past scan result by ID."""
    result = await db.execute(
        select(ScanResult).where(ScanResult.id == scan_id)
    )
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Load findings
    findings_result = await db.execute(
        select(Finding).where(Finding.scan_id == scan_id)
    )
    scan.findings = findings_result.scalars().all()

    return _scan_to_response(scan)


@router.get("/results", response_model=list[ScanResultSummary])
async def list_scan_results(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List past scan results with pagination and optional severity filter."""
    query = select(ScanResult).order_by(desc(ScanResult.created_at))

    if severity:
        query = query.where(ScanResult.severity == severity)

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    scans = result.scalars().all()

    return [
        ScanResultSummary(
            id=s.id,
            target_url=s.target_url,
            target_filename=s.target_filename,
            scan_type=s.scan_type,
            score=s.score,
            severity=s.severity,
            finding_count=s.finding_count,
            created_at=s.created_at.isoformat(),
        )
        for s in scans
    ]


@router.get("/demo-pages")
async def list_demo_pages():
    """List all available demo pages with metadata."""
    return get_demo_pages()


@router.post("/demo-pages/{page_id}/scan", response_model=ScanResultResponse)
async def scan_demo_page(page_id: str, db: AsyncSession = Depends(get_db)):
    """Scan a specific demo page by ID."""
    try:
        html_content, page_info = get_demo_page_content(page_id)
    except DemoPageNotFoundError:
        raise HTTPException(status_code=404, detail="Demo page not found")

    output = scan_html(
        html_content=html_content,
        scan_type="demo",
        target_filename=page_info["filename"],
    )

    scan = await _save_scan(db, output)

    return _scan_to_response(scan)


@router.post("/reports")
async def generate_report(request: ReportRequest, db: AsyncSession = Depends(get_db)):
    """Generate an HTML report for a completed scan."""
    result = await db.execute(
        select(ScanResult).where(ScanResult.id == request.scan_id)
    )
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Load findings
    findings_result = await db.execute(
        select(Finding).where(Finding.scan_id == request.scan_id)
    )
    scan.findings = findings_result.scalars().all()

    html_report = generate_html_report(scan)

    return HTMLResponse(
        content=html_report,
        headers={
            "Content-Disposition": f'attachment; filename="shadowscan_report_{scan.id[:8]}.html"',
        },
    )


from fastapi.responses import Response
from app.reports.generator import generate_pdf_from_html

@router.post("/reports/pdf")
async def generate_pdf_report(request: ReportRequest, db: AsyncSession = Depends(get_db)):
    """Generate a PDF report for a completed scan."""
    result = await db.execute(
        select(ScanResult).where(ScanResult.id == request.scan_id)
    )
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    findings_result = await db.execute(
        select(Finding).where(Finding.scan_id == request.scan_id)
    )
    scan.findings = findings_result.scalars().all()

    html_report = generate_html_report(scan)
    
    try:
        pdf_bytes = generate_pdf_from_html(html_report)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="shadowscan_report_{scan.id[:8]}.pdf"',
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _scan_to_response(scan: ScanResult) -> ScanResultResponse:
    """Convert a ScanResult model to an API response."""
    return ScanResultResponse(
        id=scan.id,
        target_url=scan.target_url,
        target_filename=scan.target_filename,
        scan_type=scan.scan_type,
        score=scan.score,
        severity=scan.severity,
        finding_count=scan.finding_count,
        created_at=scan.created_at.isoformat(),
        findings=[
            FindingResponse(
                id=f.id,
                source_location=f.source_location,
                matched_rule=f.matched_rule,
                matched_category=f.matched_category,
                evidence_text=f.evidence_text,
                risk_weight=f.risk_weight,
                impact=f.impact,
                remediation=f.remediation,
            )
            for f in scan.findings
        ],
    )
