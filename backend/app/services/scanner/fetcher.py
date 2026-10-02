"""SSRF-safe page fetching (blueprint 10.2).

A user-supplied URL is the most dangerous input ShadowScan accepts. Without
these controls, "scan this page" becomes "make the server read its own cloud
credentials". Every request goes through these steps:

1. Only http and https URLs, with no embedded credentials, are accepted.
2. The hostname is resolved on the server and *every* returned address is
   checked. Loopback, private, link-local, cloud metadata, multicast,
   reserved and other non-public ranges are refused, including IPv6 and
   IPv4-mapped forms. Internal-only hostnames are refused before DNS.
3. The connection goes to the address that was checked, not to the hostname
   again. This closes DNS-rebinding attacks, where a second lookup returns a
   private address. The original hostname is still sent for Host and TLS.
4. Redirects are followed by hand. Each hop repeats steps 1 to 3, with at
   most three hops.
5. The whole fetch has one deadline, and the body is read as a stream and
   cut off at the size limit after decompression.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.netguard import (  # noqa: F401 - re-exported for callers and tests
    Resolver,
    Target,
    classify_address,
    parse_target,
    pin,
    resolve_public,
    system_resolver,
)
from app.schemas.common import ErrorCode

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml", "text/plain", ""})


@dataclass
class FetchedPage:
    final_url: str
    content: bytes
    content_type: str
    redirects: list[str] = field(default_factory=list)


_HTML_ACCEPT = "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5"


def _headers(
    target: Target, address: str, settings: Settings, accept: str
) -> tuple[str, dict, dict]:
    pinned = pin(target, address)
    headers = {
        "Host": pinned.host_header,
        "User-Agent": settings.scanner_user_agent,
        "Accept": accept,
    }
    return pinned.url, headers, pinned.extensions


async def _read_capped(response: httpx.Response, limit: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large(limit)
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise _too_large(limit)
        chunks.append(chunk)
    return b"".join(chunks)


def _too_large(limit: int) -> AppError:
    return AppError(
        ErrorCode.RESPONSE_TOO_LARGE,
        f"The page is larger than the {limit // (1024 * 1024)} MB scan limit.",
        status_code=422,
    )


async def _fetch(
    url: str,
    settings: Settings,
    resolver: Resolver,
    transport: httpx.AsyncBaseTransport | None,
    *,
    accept: str = _HTML_ACCEPT,
    allowed_types: frozenset[str] | None = _HTML_TYPES,
    max_bytes: int | None = None,
) -> FetchedPage:
    redirects: list[str] = []
    current = url
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(settings.fetch_timeout_seconds),
    ) as client:
        while True:
            target = parse_target(current)
            address = await resolve_public(target, resolver)
            request_url, headers, extensions = _headers(target, address, settings, accept)

            async with client.stream(
                "GET", request_url, headers=headers, extensions=extensions
            ) as response:
                if response.status_code in _REDIRECT_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise AppError(
                            ErrorCode.FETCH_FAILED,
                            "The page redirected without a destination.",
                            status_code=422,
                        )
                    if len(redirects) >= settings.fetch_max_redirects:
                        raise AppError(
                            ErrorCode.FETCH_FAILED,
                            f"The page redirected more than {settings.fetch_max_redirects} times.",
                            status_code=422,
                        )
                    current = urljoin(current, location)
                    redirects.append(current)
                    continue

                if response.status_code >= 400:
                    raise AppError(
                        ErrorCode.FETCH_FAILED,
                        f"The site responded with HTTP {response.status_code}.",
                        status_code=422,
                    )

                content_type = (
                    response.headers.get("content-type", "").split(";")[0].strip().lower()
                )
                if allowed_types is not None and content_type not in allowed_types:
                    raise AppError(
                        ErrorCode.UNSUPPORTED_FILE_TYPE,
                        "That URL does not serve an HTML page.",
                        status_code=422,
                        detail=content_type[:100],
                    )

                content = await _read_capped(response, max_bytes or settings.fetch_max_bytes)
                return FetchedPage(
                    final_url=current,
                    content=content,
                    content_type=content_type,
                    redirects=redirects,
                )


async def fetch_page(
    url: str,
    *,
    settings: Settings | None = None,
    resolver: Resolver = system_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedPage:
    """Fetch a public web page under the full set of SSRF controls."""
    return await _guarded(url, settings, resolver, transport)


async def fetch_resource(
    url: str,
    *,
    max_bytes: int,
    settings: Settings | None = None,
    resolver: Resolver = system_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedPage:
    """Fetch a script, stylesheet or data file for the renderer.

    The same SSRF controls as a page fetch, any content type, and a size
    limit set by the caller's remaining budget.
    """
    return await _guarded(
        url, settings, resolver, transport, accept="*/*", allowed_types=None, max_bytes=max_bytes
    )


async def _guarded(
    url: str,
    settings: Settings | None,
    resolver: Resolver,
    transport: httpx.AsyncBaseTransport | None,
    **options: object,
) -> FetchedPage:
    settings = settings or get_settings()
    try:
        async with asyncio.timeout(settings.fetch_timeout_seconds):
            return await _fetch(url, settings, resolver, transport, **options)  # type: ignore[arg-type]
    except AppError:
        raise
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise AppError(
            ErrorCode.FETCH_TIMEOUT,
            f"The page did not finish loading within {settings.fetch_timeout_seconds:g} seconds.",
            status_code=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            ErrorCode.FETCH_FAILED,
            "The page could not be fetched.",
            status_code=422,
            detail=type(exc).__name__,
        ) from exc
