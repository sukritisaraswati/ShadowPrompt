"""Shared pytest fixtures.

Every test runs against an isolated temporary SQLite database created from the
ORM metadata, so the suite needs no external services and leaves no state
behind.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _test_environment(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point configuration at a throwaway database before the app is imported."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    os.environ["SHADOWPROMPT_ENV"] = "test"
    os.environ["SHADOWPROMPT_LOG_LEVEL"] = "WARNING"
    os.environ["REPORTS_DIR"] = (tmp_path_factory.mktemp("reports")).as_posix()
    # Generous by default; the rate-limit tests set their own limits.
    os.environ["RATE_LIMIT_SCANS_PER_MINUTE"] = "10000"

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
async def _schema(_test_environment: None) -> AsyncIterator[None]:
    """Create the full schema once for the session."""
    # Importing models registers the tables on the shared metadata.
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import dispose_engine, get_engine

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture
async def db_session(_schema: None):
    """An async session that rolls back whatever the test wrote."""
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        yield session
        await session.rollback()


@pytest.fixture
def client(_schema: None):
    """A synchronous test client bound to the application."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    from app.core.limits import limiter

    limiter.reset()
    yield
    limiter.reset()


async def _no_sleep(_s: float) -> None:
    return None


async def _public_resolve(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


@pytest.fixture
def use_model(client):
    """Point the Lab at a fake model: ``use_model(handler)``.

    ``handler`` receives each ``httpx.Request`` the Lab sends and returns the
    model's response, over a mock transport with a resolver that treats every
    host as public.
    """
    import httpx

    from app.api.lab.routes import get_llm_backend
    from app.main import app
    from app.services.lab.llm_client import LlmBackend

    def install(handler) -> None:
        app.dependency_overrides[get_llm_backend] = lambda: LlmBackend(
            transport=httpx.MockTransport(handler), resolver=_public_resolve, sleep=_no_sleep
        )

    yield install
    app.dependency_overrides.pop(get_llm_backend, None)
