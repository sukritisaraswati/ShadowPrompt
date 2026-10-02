"""Turn a rendered HTML report into a stored file and a download response."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.db.models import Report, ReportFormat, ReportType
from app.services.reports.pdf import render_pdf
from app.services.reports.scan_report import REPORT_CSP


async def deliver_report(
    db: AsyncSession,
    *,
    report_type: ReportType,
    reference_id: uuid.UUID,
    html: str,
    fmt: str,
    stem: str,
) -> Response:
    """Render to the requested format, keep a copy on disk, and return it."""
    if fmt == "pdf":
        # PDF rendering is CPU-bound and can take a second or two.
        content: bytes = await run_in_threadpool(render_pdf, html)
        media_type, report_format, suffix = "application/pdf", ReportFormat.PDF, "pdf"
    else:
        content = html.encode("utf-8")
        media_type, report_format, suffix = "text/html; charset=utf-8", ReportFormat.HTML, "html"

    directory = Path(get_settings().reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}-{reference_id}-{uuid.uuid4().hex[:8]}.{suffix}"
    path.write_bytes(content)
    db.add(
        Report(
            type=report_type,
            reference_id=reference_id,
            format=report_format,
            file_path=str(path),
        )
    )

    headers = {
        "Content-Disposition": f'attachment; filename="{stem}-{str(reference_id)[:8]}.{suffix}"'
    }
    if fmt == "html":
        headers["Content-Security-Policy"] = REPORT_CSP
    return Response(content=content, media_type=media_type, headers=headers)
