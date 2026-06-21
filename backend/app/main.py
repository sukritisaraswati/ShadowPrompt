"""
ShadowPrompt — LLM Security Testing Lab
FastAPI application entry point for the ShadowScan MVP.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db

# Track server start time for health endpoint
_start_time: datetime = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup."""
    global _start_time
    _start_time = datetime.now(timezone.utc)
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Defensive LLM Security Testing Lab — ShadowScan Webpage Scanner",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.routers import scan, health, lab  # noqa: E402

app.include_router(scan.router, prefix="/api/v1/scan", tags=["ShadowScan"])
app.include_router(lab.router, prefix="/api/v1/lab", tags=["ShadowPrompt Lab"])
app.include_router(health.router, prefix="/api/v1", tags=["Health"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "service": "ShadowScan",
        "docs": "/docs",
    }


def get_start_time() -> datetime:
    """Get server start time for uptime calculation."""
    return _start_time
