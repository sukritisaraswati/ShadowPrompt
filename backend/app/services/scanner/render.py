"""Optional JavaScript rendering, so content added after page load is scanned.

Static extraction sees only the HTML the server sent. A page can add its
injected instruction with a script once it loads, and an LLM agent that reads
the live page sees it while a static scanner does not. When rendering is
enabled, the page is also loaded in headless Chromium and the resulting DOM is
scanned.

The browser is sandboxed from the network:

* It is launched with every connection pointed at a dead proxy, so nothing it
  tries on its own (WebSockets, prefetches, beacons) leaves the machine.
* Every request it makes is intercepted. The page itself is served from the
  HTML ShadowScan already fetched. Scripts, stylesheets, frames and XHR/fetch
  GETs are fetched on its behalf by the same SSRF-guarded fetcher used for
  pages, so private and metadata addresses stay unreachable, with a cap on the
  number of requests and total bytes. Other methods, and images, fonts and
  media, are refused.
* Service workers, downloads and permission prompts are disabled, dialogs are
  dismissed, and the whole render has a deadline.

The page's JavaScript is hostile by assumption, so Chromium's own process
sandbox is on by default. In a container that forbids it (no-new-privileges,
no user namespaces), set ``SCANNER_RENDER_CHROMIUM_SANDBOX=false`` and rely on
the container's isolation instead.

Rendering needs the ``render`` extra (Playwright) and a Chromium install, and
is off unless ``SCANNER_RENDER_ENABLED`` is set.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.scanner.fetcher import Resolver, fetch_resource, system_resolver

# Where uploaded files are "served" from inside the sandbox. The .invalid TLD
# can never resolve, so nothing at this origin is ever fetched for real.
UPLOAD_ORIGIN = "https://upload.shadowscan.invalid/"
DEAD_PROXY = "http://127.0.0.1:9"
_FETCHED_TYPES = frozenset({"document", "script", "stylesheet", "xhr", "fetch"})
_SETTLE_SECONDS = 0.5

_semaphore: asyncio.Semaphore | None = None


@dataclass
class RenderResult:
    html: str | None
    requests: int = 0
    blocked: int = 0
    truncated: bool = False
    error: str | None = None
    blocked_reasons: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        return {
            "requests": self.requests,
            "blocked": self.blocked,
            "truncated": self.truncated,
            "error": self.error,
        }


class Renderer(Protocol):
    async def render(self, html: str, base_url: str | None) -> RenderResult: ...


def render_available(settings: Settings | None = None) -> bool:
    """True when rendering is switched on and Playwright is installed."""
    settings = settings or get_settings()
    return settings.scanner_render_enabled and importlib.util.find_spec("playwright") is not None


def _limit(settings: Settings) -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.scanner_render_max_concurrent))
    return _semaphore


class _Budget:
    def __init__(self, settings: Settings) -> None:
        self.requests_left = settings.scanner_render_max_requests
        self.bytes_left = settings.scanner_render_max_bytes


class ChromiumRenderer:
    """Renders with Playwright's Chromium under the controls described above."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        resolver: Resolver = system_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.resolver = resolver
        self.transport = transport

    async def render(self, html: str, base_url: str | None) -> RenderResult:
        result = RenderResult(html=None)
        try:
            async with _limit(self.settings):
                async with asyncio.timeout(self.settings.scanner_render_timeout_seconds):
                    result.html = await self._render(html, base_url or UPLOAD_ORIGIN, result)
        except TimeoutError:
            result.error = (
                f"Rendering did not finish within "
                f"{self.settings.scanner_render_timeout_seconds:g} seconds."
            )
        except Exception as exc:  # noqa: BLE001 - a broken render must not break the scan
            result.error = f"Rendering failed ({type(exc).__name__})."
        return result

    async def _render(self, html: str, document_url: str, result: RenderResult) -> str:
        from playwright.async_api import async_playwright

        budget = _Budget(self.settings)
        served_document = False

        def block(reason: str) -> None:
            result.blocked += 1
            result.blocked_reasons[reason] = result.blocked_reasons.get(reason, 0) + 1

        async def handle(route, request) -> None:  # noqa: ANN001 - Playwright types
            nonlocal served_document
            if (
                not served_document
                and request.is_navigation_request()
                and (request.url == document_url)
            ):
                served_document = True
                await route.fulfill(status=200, body=html, content_type="text/html; charset=utf-8")
                return
            if request.method != "GET":
                block("method")
                await route.abort()
                return
            if request.resource_type not in _FETCHED_TYPES:
                block("type")
                await route.abort()
                return
            if request.url.startswith(UPLOAD_ORIGIN):
                block("upload origin")
                await route.abort()
                return
            if budget.requests_left <= 0 or budget.bytes_left <= 0:
                result.truncated = True
                block("budget")
                await route.abort()
                return
            budget.requests_left -= 1
            try:
                fetched = await fetch_resource(
                    request.url,
                    max_bytes=budget.bytes_left,
                    settings=self.settings,
                    resolver=self.resolver,
                    transport=self.transport,
                )
            except AppError as exc:
                block(exc.code.value.lower())
                await route.abort()
                return
            budget.bytes_left -= len(fetched.content)
            result.requests += 1
            await route.fulfill(
                status=200,
                body=fetched.content,
                content_type=fetched.content_type or "application/octet-stream",
            )

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                # Chromium's own process sandbox, on unless the deployment
                # runs it inside a container that forbids it (see settings).
                chromium_sandbox=self.settings.scanner_render_chromium_sandbox,
                proxy={"server": DEAD_PROXY},
                args=[
                    "--disable-background-networking",
                    "--disable-sync",
                    "--no-first-run",
                    # Containers often have a tiny /dev/shm; use /tmp instead.
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                context = await browser.new_context(
                    java_script_enabled=True,
                    service_workers="block",
                    accept_downloads=False,
                    user_agent=self.settings.scanner_user_agent,
                    viewport={"width": 1280, "height": 900},
                )
                await context.route("**/*", handle)
                page = await context.new_page()
                page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))
                await page.goto(document_url, wait_until="load")
                with contextlib.suppress(Exception):
                    await page.wait_for_load_state("networkidle", timeout=3_000)
                # Give timers a moment to add their content.
                await asyncio.sleep(_SETTLE_SECONDS)
                return await page.content()
            finally:
                await browser.close()


def get_renderer() -> Renderer:
    return ChromiumRenderer()
