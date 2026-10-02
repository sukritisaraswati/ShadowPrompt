"""Public route for hosted attack pages: ``/p/{key}/{slug}``.

Outside ``/api`` on purpose: this is what a user's chatbot fetches when it
follows the link in an indirect test, so it must look like an ordinary page.
Every response carries the defensive headers from
:mod:`app.services.lab.hosted_pages`, and unknown or expired links are 404s.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.limits import hosted_page_rate_limit
from app.db.session import get_db
from app.schemas.common import ErrorCode
from app.services.lab.hosted_pages import PAGE_HEADERS, record_fetch

router = APIRouter(tags=["hosted pages"])


@router.get(
    "/p/{key}/{slug}",
    response_class=HTMLResponse,
    summary="A hosted attack page",
    include_in_schema=False,
    dependencies=[Depends(hosted_page_rate_limit)],
)
async def hosted_page(
    key: str, slug: str, request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    if len(key) > 64:
        raise AppError(ErrorCode.NOT_FOUND, "Not found.", status_code=404)
    page = await record_fetch(db, key, request.headers.get("user-agent"))
    if page is None:
        raise AppError(ErrorCode.NOT_FOUND, "Not found.", status_code=404)
    return HTMLResponse(page.html, headers=PAGE_HEADERS)
