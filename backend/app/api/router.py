"""Aggregate router for the versioned API surface.

Lab and ShadowScan share one backend but keep separate route groups, as the
blueprint specifies. ``/health`` sits outside the version prefix so uptime
checks never break on a version bump.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.lab.routes import router as lab_router
from app.api.scan.routes import router as scan_router

api_v1_router = APIRouter()
api_v1_router.include_router(lab_router)
api_v1_router.include_router(scan_router)

__all__ = ["api_v1_router"]
