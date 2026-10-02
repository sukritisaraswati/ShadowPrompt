"""Async database engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs(settings: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"echo": settings.database_echo, "future": True}
    if settings.is_sqlite:
        # SQLite has no server-side pool to configure, and the aiosqlite driver
        # needs cross-thread access for the FastAPI worker model.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)
    return kwargs


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, **_engine_kwargs(settings))
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine and reset module state (used on shutdown and in tests)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
