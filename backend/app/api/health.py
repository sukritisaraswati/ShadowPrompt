"""Platform health check -- ``GET /health`` (blueprint section 9.2)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.schemas.common import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["platform"])

_STARTED_AT = time.monotonic()


async def _check_database() -> ServiceStatus:
    """Probe the database with a trivial query."""
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return ServiceStatus.OK
    except Exception:
        # Logged without the exception text, which could carry a DSN.
        logger.warning("Database health probe failed")
        return ServiceStatus.DOWN


@router.get("/health", response_model=HealthResponse, summary="Platform health check")
async def health() -> HealthResponse:
    """Report version, uptime and database status."""
    settings = get_settings()
    database = await _check_database()
    return HealthResponse(
        status=ServiceStatus.OK if database is ServiceStatus.OK else ServiceStatus.DEGRADED,
        version=__version__,
        environment=settings.shadowprompt_env,
        uptime_seconds=round(time.monotonic() - _STARTED_AT, 3),
        database=database,
        timestamp=datetime.now(UTC),
    )
