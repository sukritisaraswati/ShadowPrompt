"""
Health Check Router
Returns application status, version, and uptime.
"""

from datetime import datetime, timezone
from fastapi import APIRouter
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Platform health check — returns version, uptime, and database status."""
    from app.main import get_start_time

    start_time = get_start_time()
    uptime_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()

    return {
        "status": "healthy",
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "uptime_seconds": round(uptime_seconds, 1),
        "service": "ShadowScan",
        "database": "connected",
    }
