"""
ShadowScan URL Fetcher
Async URL fetching with comprehensive SSRF protection.
Validates schemes, resolves DNS, checks IPs against blocklist, re-validates redirects.
"""

import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple

import httpx

from app.config import settings, BLOCKED_NETWORKS


class FetchError(Exception):
    """Custom exception for fetch errors with user-friendly error codes."""
    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


def validate_url_scheme(url: str) -> None:
    """Validate that the URL uses an allowed scheme."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in settings.ALLOWED_SCHEMES:
        raise FetchError(
            f"URL scheme '{parsed.scheme}' is not allowed. Only HTTP and HTTPS are supported.",
            "INVALID_SCHEME",
        )
    if not parsed.hostname:
        raise FetchError(
            "URL must have a valid hostname.",
            "INVALID_URL",
        )


def is_ip_blocked(ip_str: str) -> bool:
    """Check if an IP address falls within any blocked network range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in BLOCKED_NETWORKS:
            if ip in network:
                return True
        return False
    except ValueError:
        return True  # Invalid IPs are blocked


async def resolve_and_validate(hostname: str) -> str:
    """
    Resolve hostname to IP and validate it's not in a blocked range.
    Returns the resolved IP address.
    """
    try:
        # Resolve DNS
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        if not addr_info:
            raise FetchError(
                f"Could not resolve hostname: {hostname}",
                "DNS_RESOLUTION_FAILED",
            )

        # Check ALL resolved IPs (not just the first)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            if is_ip_blocked(ip_str):
                raise FetchError(
                    f"Target address is blocked. Private, loopback, link-local, and cloud metadata addresses are not allowed.",
                    "BLOCKED_TARGET",
                )

        return addr_info[0][4][0]  # Return first resolved IP

    except socket.gaierror:
        raise FetchError(
            f"Could not resolve hostname: {hostname}",
            "DNS_RESOLUTION_FAILED",
        )


async def fetch_url(url: str) -> Tuple[str, str]:
    """
    Fetch HTML content from a URL with full SSRF protection.

    Returns:
        (html_content, final_url) tuple

    Raises:
        FetchError: On any validation or fetch failure
    """
    # Step 1: Validate URL scheme
    validate_url_scheme(url)

    # Step 2: Resolve DNS and validate IP
    parsed = urlparse(url)
    await resolve_and_validate(parsed.hostname)

    # Step 3: Fetch with redirect validation
    redirect_count = 0
    current_url = url

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.URL_TIMEOUT),
        follow_redirects=False,  # We handle redirects manually for re-validation
        max_redirects=0,
        verify=True,
    ) as client:
        while True:
            try:
                response = await client.get(
                    current_url,
                    headers={
                        "User-Agent": f"ShadowScan/{settings.APP_VERSION} (Security Scanner)",
                        "Accept": "text/html,application/xhtml+xml,*/*",
                    },
                )
            except httpx.TimeoutException:
                raise FetchError(
                    f"Request timed out after {settings.URL_TIMEOUT} seconds.",
                    "TIMEOUT",
                )
            except httpx.ConnectError:
                raise FetchError(
                    "Could not connect to the target URL.",
                    "CONNECTION_FAILED",
                )
            except httpx.RequestError as e:
                raise FetchError(
                    f"Request failed: {str(e)}",
                    "REQUEST_FAILED",
                )

            # Handle redirects manually
            if response.is_redirect:
                redirect_count += 1
                if redirect_count > settings.MAX_REDIRECTS:
                    raise FetchError(
                        f"Too many redirects (max {settings.MAX_REDIRECTS}).",
                        "TOO_MANY_REDIRECTS",
                    )

                # Get redirect target
                redirect_url = str(response.next_request.url) if response.next_request else None
                if not redirect_url:
                    location = response.headers.get("location", "")
                    if not location:
                        raise FetchError(
                            "Redirect without Location header.",
                            "INVALID_REDIRECT",
                        )
                    # Handle relative redirects
                    if location.startswith("/"):
                        parsed_current = urlparse(current_url)
                        redirect_url = f"{parsed_current.scheme}://{parsed_current.netloc}{location}"
                    else:
                        redirect_url = location

                # Re-validate the redirect target (SSRF re-check)
                validate_url_scheme(redirect_url)
                redirect_parsed = urlparse(redirect_url)
                await resolve_and_validate(redirect_parsed.hostname)

                current_url = redirect_url
                continue

            # Non-redirect response
            break

        # Step 4: Validate response
        if response.status_code != 200:
            raise FetchError(
                f"Server returned status {response.status_code}.",
                "HTTP_ERROR",
            )

        # Check content length
        content_length = len(response.content)
        if content_length > settings.MAX_URL_RESPONSE_SIZE:
            raise FetchError(
                f"Response size ({content_length} bytes) exceeds the {settings.MAX_URL_RESPONSE_SIZE // (1024*1024)}MB limit.",
                "RESPONSE_TOO_LARGE",
            )

        # Check content type (warn but don't block — some sites misconfigure headers)
        content_type = response.headers.get("content-type", "")
        html_content = response.text

        return html_content, str(response.url)
