"""Security tests for the SSRF-guarded fetcher (blueprint 10.2).

DNS and HTTP are both faked, so these tests never touch the network and can
assert exactly which address a request was sent to.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.scanner.fetcher import classify_address, fetch_page, parse_target

pytestmark = pytest.mark.security

PUBLIC_IP = "93.184.216.34"
PAGE = b"<html><body><p>hello</p></body></html>"


def make_resolver(table: dict[str, list[str]]):
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such host")
        return table[host]

    return resolve


def settings(**overrides) -> Settings:
    base = dict(fetch_timeout_seconds=5, fetch_max_redirects=3, fetch_max_bytes=1024)
    base.update(overrides)
    return Settings(**base)


def html_response(body: bytes = PAGE, **headers) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html", **headers}, content=body)


async def fetch(url: str, handler, dns: dict[str, list[str]], **kw):
    return await fetch_page(
        url,
        settings=settings(**kw),
        resolver=make_resolver(dns),
        transport=httpx.MockTransport(handler),
    )


def never_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"request should have been blocked: {request.url}")


# --------------------------------------------------------------------------- #
# Address classification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("address", "reason"),
    [
        ("127.0.0.1", "loopback"),
        ("127.255.255.254", "loopback"),
        ("::1", "loopback"),
        ("10.0.0.5", "private"),
        ("172.16.0.1", "private"),
        ("172.31.255.255", "private"),
        ("192.168.1.1", "private"),
        ("169.254.169.254", "metadata"),
        ("169.254.10.10", "link-local"),
        ("fe80::1", "link-local"),
        ("fc00::1", "private"),
        ("0.0.0.0", "unspecified"),
        ("::", "unspecified"),
        ("100.64.0.1", "non-public"),
        ("224.0.0.1", "multicast"),
        ("::ffff:127.0.0.1", "loopback"),
        ("::ffff:169.254.169.254", "metadata"),
        ("2002:7f00:0001::", "loopback"),  # 6to4 wrapping 127.0.0.1
        ("fd00:ec2::254", "metadata"),
    ],
)
def test_non_public_addresses_are_classified(address: str, reason: str) -> None:
    result = classify_address(address)
    assert result is not None and reason in result


@pytest.mark.parametrize("address", [PUBLIC_IP, "1.1.1.1", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert classify_address(address) is None


# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "gopher://x/",
        "data:text/html,x",
    ],
)
def test_non_http_schemes_are_blocked(url: str) -> None:
    with pytest.raises(AppError) as info:
        parse_target(url)
    assert info.value.code == "BLOCKED_TARGET"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://LOCALHOST:8000/",
        "http://app.localhost/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://printer.local/",
    ],
)
def test_internal_host_names_are_blocked_before_dns(url: str) -> None:
    with pytest.raises(AppError) as info:
        parse_target(url)
    assert info.value.code == "BLOCKED_TARGET"


@pytest.mark.parametrize(
    "url", ["", "   ", "http://", "https://user:pass@example.com/", "http://example.com:99999/"]
)
def test_malformed_or_credentialed_urls_are_rejected(url: str) -> None:
    with pytest.raises(AppError) as info:
        parse_target(url)
    assert info.value.code == "VALIDATION_ERROR"


def test_overlong_url_is_rejected() -> None:
    with pytest.raises(AppError):
        parse_target("https://example.com/" + "a" * 3000)


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("url", "dns"),
    [
        ("http://127.0.0.1/", {"127.0.0.1": ["127.0.0.1"]}),
        ("http://169.254.169.254/latest/meta-data/", {"169.254.169.254": ["169.254.169.254"]}),
        ("http://[::1]/", {"::1": ["::1"]}),
        ("http://2130706433/", {"2130706433": ["127.0.0.1"]}),  # decimal-encoded loopback
        ("http://internal.example/", {"internal.example": ["10.1.2.3"]}),
        ("http://sneaky.example/", {"sneaky.example": ["::ffff:192.168.0.1"]}),
    ],
)
async def test_non_public_targets_are_never_requested(url: str, dns) -> None:
    with pytest.raises(AppError) as info:
        await fetch(url, never_called, dns)
    assert info.value.code == "BLOCKED_TARGET"


async def test_any_private_address_in_the_answer_blocks_the_request() -> None:
    """DNS round-robin with one private record must not slip through."""
    with pytest.raises(AppError) as info:
        await fetch(
            "http://mixed.example/", never_called, {"mixed.example": [PUBLIC_IP, "10.0.0.1"]}
        )
    assert info.value.code == "BLOCKED_TARGET"


async def test_connection_is_pinned_to_the_checked_address() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return html_response()

    page = await fetch("https://example.com/path?q=1", handler, {"example.com": [PUBLIC_IP]})

    assert page.content == PAGE
    request = seen[0]
    assert request.url.host == PUBLIC_IP
    assert request.url.path == "/path" and request.url.query == b"q=1"
    assert request.headers["host"] == "example.com"
    assert request.extensions["sni_hostname"] == "example.com"


async def test_redirect_to_private_address_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == PUBLIC_IP:
            return httpx.Response(302, headers={"location": "http://evil.example/admin"})
        raise AssertionError("the private hop must never be requested")

    with pytest.raises(AppError) as info:
        await fetch(
            "http://public.example/",
            handler,
            {"public.example": [PUBLIC_IP], "evil.example": ["192.168.0.10"]},
        )
    assert info.value.code == "BLOCKED_TARGET"


async def test_redirect_to_metadata_ip_literal_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": "http://169.254.169.254/"})

    with pytest.raises(AppError) as info:
        await fetch("http://public.example/", handler, {"public.example": [PUBLIC_IP]})
    assert info.value.code == "BLOCKED_TARGET"


async def test_relative_redirects_are_followed_and_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return html_response()

    page = await fetch("http://public.example/start", handler, {"public.example": [PUBLIC_IP]})
    assert page.final_url == "http://public.example/final"
    assert page.redirects == ["http://public.example/final"]


async def test_redirect_limit_is_enforced() -> None:
    hops = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal hops
        hops += 1
        return httpx.Response(302, headers={"location": f"/hop{hops}"})

    with pytest.raises(AppError) as info:
        await fetch("http://public.example/", handler, {"public.example": [PUBLIC_IP]})
    assert info.value.code == "FETCH_FAILED"
    assert hops == 4  # the original request plus three permitted redirects


async def test_oversized_body_is_cut_off() -> None:
    with pytest.raises(AppError) as info:
        await fetch(
            "http://public.example/",
            lambda r: html_response(b"x" * 5000),
            {"public.example": [PUBLIC_IP]},
            fetch_max_bytes=1024,
        )
    assert info.value.code == "RESPONSE_TOO_LARGE"


async def test_declared_oversized_length_is_refused() -> None:
    with pytest.raises(AppError) as info:
        await fetch(
            "http://public.example/",
            lambda r: html_response(b"small", **{"content-length": "999999999"}),
            {"public.example": [PUBLIC_IP]},
        )
    assert info.value.code == "RESPONSE_TOO_LARGE"


async def test_non_html_content_is_refused() -> None:
    with pytest.raises(AppError) as info:
        await fetch(
            "http://public.example/",
            lambda r: httpx.Response(
                200, headers={"content-type": "application/pdf"}, content=b"%PDF"
            ),
            {"public.example": [PUBLIC_IP]},
        )
    assert info.value.code == "UNSUPPORTED_FILE_TYPE"


async def test_error_status_is_reported() -> None:
    with pytest.raises(AppError) as info:
        await fetch(
            "http://public.example/", lambda r: httpx.Response(404), {"public.example": [PUBLIC_IP]}
        )
    assert info.value.code == "FETCH_FAILED"
    assert "404" in info.value.message


async def test_timeout_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AppError) as info:
        await fetch("http://public.example/", handler, {"public.example": [PUBLIC_IP]})
    assert info.value.code == "FETCH_TIMEOUT"


async def test_unresolvable_host_is_reported() -> None:
    with pytest.raises(AppError) as info:
        await fetch("http://nowhere.example/", never_called, {})
    assert info.value.code == "FETCH_FAILED"
