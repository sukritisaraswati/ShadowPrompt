"""Abuse controls: request body size limits and per-client rate limiting."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.common import ErrorCode

# Room for multipart boundaries and headers around the file itself.
MULTIPART_OVERHEAD = 64 * 1024
DEFAULT_BODY_LIMIT = 256 * 1024
UPLOAD_PATH = "/api/v1/scan/html"


def _body_limit_for(path: str) -> int:
    if path == UPLOAD_PATH:
        return get_settings().upload_max_bytes + MULTIPART_OVERHEAD
    return DEFAULT_BODY_LIMIT


def _too_large_body(limit: int) -> bytes:
    return json.dumps(
        {
            "code": ErrorCode.UPLOAD_TOO_LARGE.value,
            "message": "The request body is too large.",
            "detail": f"Limit is {limit} bytes.",
        }
    ).encode()


class BodySizeLimitMiddleware:
    """Reject oversized bodies before application code reads them.

    A declared Content-Length over the limit is refused immediately. A body
    without one, such as a chunked upload, is counted as it streams and cut
    off the moment it passes the limit, so nothing large is ever spooled.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        limit = _body_limit_for(scope["path"])
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": _too_large_body(limit)})
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # FastAPI re-raises HTTPException from body parsing, and
                    # the app's handler maps 413 to UPLOAD_TOO_LARGE.
                    raise HTTPException(status_code=413, detail="The request body is too large.")
            return message

        await self.app(scope, limited_receive, send)


class SlidingWindowRateLimiter:
    """In-process sliding-window limiter keyed by bucket and client.

    Adequate for a single backend process. A multi-process deployment would
    move this state to a shared store such as Redis.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, bucket: str, client: str, limit: int, window_seconds: float) -> float | None:
        """Record a hit. Returns ``None`` if allowed, else seconds until retry."""
        now = self._clock()
        key = (bucket, client)
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return max(0.0, window_seconds - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > 10_000:
                self._prune(now, window_seconds)
            return None

    def _prune(self, now: float, window_seconds: float) -> None:
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] >= window_seconds]
        for key in stale:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowRateLimiter()


def client_address(request: Request) -> str:
    # Behind the bundled nginx, uvicorn's --proxy-headers sets this from
    # X-Forwarded-For. It is never read from a raw header here.
    return request.client.host if request.client else "unknown"


def _enforce(request: Request, bucket: str, limit: int, window: float, what: str) -> None:
    retry_after = limiter.hit(bucket, client_address(request), limit, window)
    if retry_after is not None:
        seconds = max(1, int(retry_after + 0.999))
        raise AppError(
            ErrorCode.RATE_LIMITED,
            f"Too many {what}. Please wait before trying again.",
            status_code=429,
            detail=f"Retry in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )


def scan_rate_limit(request: Request) -> None:
    """FastAPI dependency limiting scans per client per minute."""
    _enforce(request, "scan", get_settings().rate_limit_scans_per_minute, 60.0, "scans")


def connect_rate_limit(request: Request) -> None:
    """Connection tests send a real request to the user's model, so they are limited too."""
    _enforce(request, "connect", 20, 60.0, "connection tests")


def campaign_rate_limit(request: Request) -> None:
    """Campaign launches per client per hour (blueprint 10.5)."""
    _enforce(request, "campaign", get_settings().rate_limit_campaigns_per_hour, 3600.0, "campaigns")
