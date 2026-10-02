"""Outbound network guard shared by every server-side request (blueprint 10.2, 10.3).

Both ShadowScan's page fetcher and the Lab's LLM proxy send requests to
addresses a user typed in. Without these checks either one becomes a way to
make the server talk to its own internal network or cloud metadata service.

The guard:

1. Accepts only http and https URLs with no embedded credentials, and refuses
   internal-only host names before any lookup.
2. Resolves the host on the server and checks *every* returned address,
   refusing loopback, private, link-local, cloud metadata, multicast, reserved
   and other non-public ranges, including IPv6 and IPv4-mapped forms.
3. Produces a request aimed at the address that was checked, so a second DNS
   lookup cannot swap in a private address (DNS rebinding). The real host name
   is still sent for the Host header and for TLS verification.

``allow_private`` relaxes only step 2 and the internal-name check. It exists
for self-hosted deployments testing local models, is off by default, and is
never enabled for ShadowScan.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.errors import AppError
from app.schemas.common import ErrorCode

Resolver = Callable[[str, int], Awaitable[list[str]]]

MAX_URL_LENGTH = 2048
_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")
_BLOCKED_HOSTS = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})
_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("169.254.170.2"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)


@dataclass(frozen=True)
class Target:
    url: str
    scheme: str
    host: str
    port: int
    path: str

    @property
    def default_port(self) -> int:
        return 443 if self.scheme == "https" else 80


@dataclass(frozen=True)
class PinnedRequest:
    url: str
    host_header: str
    extensions: dict[str, str]


def blocked(reason: str) -> AppError:
    return AppError(
        ErrorCode.BLOCKED_TARGET,
        "This address points to a private or internal network and cannot be reached.",
        status_code=400,
        detail=reason,
    )


def _invalid(message: str) -> AppError:
    return AppError(ErrorCode.VALIDATION_ERROR, message, status_code=400)


def parse_target(url: str, *, allow_private: bool = False) -> Target:
    """Validate the shape of a URL. Does not touch the network."""
    url = url.strip()
    if not url:
        raise _invalid("Enter a URL.")
    if len(url) > MAX_URL_LENGTH:
        raise _invalid(f"URLs longer than {MAX_URL_LENGTH} characters are not accepted.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise _invalid("That URL could not be parsed.") from exc

    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise blocked(f"scheme '{scheme or 'none'}' is not allowed; use http or https")
    if parts.username is not None or parts.password is not None:
        raise _invalid("URLs containing a username or password are not accepted.")

    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise _invalid("That URL has no host name.")
    try:
        host.encode("idna")
    except UnicodeError as exc:
        raise _invalid("That host name is not valid.") from exc

    if not allow_private and (host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_HOST_SUFFIXES)):
        raise blocked("internal host name")

    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return Target(
        url=url,
        scheme=scheme,
        host=host,
        port=port or (443 if scheme == "https" else 80),
        path=path,
    )


def classify_address(address: str) -> str | None:
    """Why an address may not be contacted, or ``None`` if it is public."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return "unparseable address"

    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None:
            reason = classify_address(str(embedded))
            return f"{reason} (embedded in IPv6)" if reason else None

    if ip in _METADATA_ADDRESSES:
        return "cloud metadata endpoint"
    if ip.is_loopback:
        return "loopback"
    if ip.is_unspecified:
        return "unspecified address"
    if ip.is_link_local:
        return "link-local"
    if ip.is_private:
        return "private network"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved range"
    if not ip.is_global:
        return "non-public range"
    return None


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


def _check(address: str, allow_private: bool) -> None:
    reason = classify_address(address)
    if reason is None:
        return
    # Cloud metadata is never reachable, even when private ranges are allowed.
    if allow_private and "metadata" not in reason and "unparseable" not in reason:
        return
    raise blocked(reason)


async def resolve_public(target: Target, resolver: Resolver, *, allow_private: bool = False) -> str:
    """Resolve the host and return an address, refusing if *any* is disallowed."""
    literal = target.host.strip("[]")
    try:
        ipaddress.ip_address(literal)
    except ValueError:
        pass
    else:
        # An IP literal needs no lookup, and must not depend on one to be checked.
        _check(literal, allow_private)
        return literal
    try:
        addresses = await resolver(target.host, target.port)
    except (OSError, UnicodeError) as exc:
        raise AppError(
            ErrorCode.FETCH_FAILED,
            "The host name could not be resolved.",
            status_code=422,
            detail=target.host,
        ) from exc
    if not addresses:
        raise AppError(ErrorCode.FETCH_FAILED, "The host name has no addresses.", status_code=422)
    for address in addresses:
        _check(address, allow_private)
    return addresses[0]


def pin(target: Target, address: str) -> PinnedRequest:
    """A request URL aimed at the checked address, keeping the real host name."""
    literal = f"[{address}]" if ":" in address else address
    host_header = (
        target.host if target.port == target.default_port else f"{target.host}:{target.port}"
    )
    # TLS must be negotiated and verified against the real host name.
    extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
    return PinnedRequest(
        url=f"{target.scheme}://{literal}:{target.port}{target.path}",
        host_header=host_header,
        extensions=extensions,
    )
