"""FastAPI application factory and entrypoint.

Wires together configuration, redacting logging, the database lifecycle, CORS,
baseline security headers, a uniform error envelope, and the two route groups.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.health import router as health_router
from app.api.hosted.routes import router as hosted_router
from app.api.router import api_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.limits import BodySizeLimitMiddleware
from app.core.logging import configure_logging
from app.db.session import dispose_engine
from app.schemas.common import ErrorCode, ErrorResponse
from app.services.lab.orchestrator import recover_orphans, registry
from app.services.lab.payloads import get_library
from app.services.scanner.rules import get_rules

logger = logging.getLogger(__name__)

DESCRIPTION = """
Defensive LLM security testing platform.

* **ShadowPrompt Lab** -- connect an LLM and run escalating attack campaigns (levels 1-5).
* **ShadowScan** -- statically analyse a webpage for content that could manipulate an LLM.

For authorized, educational, and defensive security research only.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down hooks."""
    settings = get_settings()
    logger.info(
        "Starting %s v%s (env=%s, database=%s)",
        settings.app_name,
        __version__,
        settings.shadowprompt_env,
        "sqlite" if settings.is_sqlite else "postgresql",
    )
    # Load and validate detection rules now, so a broken rule file stops
    # startup instead of silently weakening every scan.
    rules = get_rules()
    logger.info("Loaded %d ShadowScan detection rules", len(rules.rules))
    library = get_library()
    logger.info("Loaded %d Lab payloads", len(library.payloads))
    try:
        recovered = await recover_orphans()
    except Exception:
        # A missing table (migrations not applied yet) must not block startup.
        logger.warning("Could not check for interrupted campaigns")
    else:
        if recovered:
            logger.warning("Marked %d interrupted campaign(s) as failed", recovered)
    yield
    await registry.shutdown()
    await dispose_engine()
    logger.info("Shutdown complete")


def _register_error_handlers(app: FastAPI) -> None:
    """Return every error in the shared envelope, leaking nothing internal."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        body = ErrorResponse(code=exc.code, message=exc.message, detail=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(mode="json"),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INTERNAL_ERROR
        if exc.status_code == 429:
            code = ErrorCode.RATE_LIMITED
        elif exc.status_code == 413:
            code = ErrorCode.UPLOAD_TOO_LARGE
        elif exc.status_code == 501:
            code = ErrorCode.NOT_IMPLEMENTED
        body = ErrorResponse(code=code, message=str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            detail=f"{len(exc.errors())} field(s) rejected",
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # The traceback goes to the (redacting) logger; the client gets nothing
        # that could reveal configuration, paths or credentials.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        body = ErrorResponse(code=ErrorCode.INTERNAL_ERROR, message="An internal error occurred")
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    # Added first so it sits innermost: the security-header and CORS layers
    # still wrap its 413 responses.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Baseline hardening headers on every response.

        The API itself returns JSON, but generated reports are HTML containing
        attacker-controlled evidence strings, so a restrictive default-src is
        set globally rather than per-route.
        """
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


def create_app() -> FastAPI:
    """Build and configure the application."""
    settings = get_settings()
    configure_logging(settings.shadowprompt_log_level)

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.shadowprompt_debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.shadowprompt_debug else None,
    )

    _register_middleware(app, settings)
    _register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(hosted_router)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
