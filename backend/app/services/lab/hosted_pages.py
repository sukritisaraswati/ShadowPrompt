"""Hosted attack pages: indirect injection delivered the way it happens for real.

For a chatbot that can browse, pasting a page into the message is only a
simulation. With hosted delivery, ShadowPrompt serves each indirect test's
page at its own URL and asks the bot to read it, so the instruction arrives
through the bot's real fetching path.

Every fetch is recorded. A bot that never fetched its page was never exposed
to the instruction, so that test is reported as Unclear with the reason,
instead of a misleading Pass.

The pages are attack content (and, for custom packs, user-supplied HTML), so
they are served defensively: an unguessable link per page, a 24-hour expiry,
a sandboxing Content-Security-Policy that disables scripts, forms and
navigation, no indexing, no caching, and a per-client rate limit.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HostedPage
from app.db.session import get_sessionmaker
from app.services.lab.payloads import Payload, Track

# Scripts, forms, plugins, popups and top-level navigation are all disabled.
PAGE_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
PAGE_HEADERS = {
    "Content-Security-Policy": PAGE_CSP,
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class FetchStatus:
    fetch_count: int
    first_fetched_at: datetime | None
    user_agent: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "fetched": self.fetch_count > 0,
            "fetch_count": self.fetch_count,
            "first_fetched_at": self.first_fetched_at.isoformat()
            if self.first_fetched_at
            else None,
            "user_agent": self.user_agent,
        }


def slug_for(payload: Payload) -> str:
    """A readable last path segment, so the link looks like an ordinary page."""
    path = urlsplit(payload.spec.page_url or "").path.rstrip("/")
    name = path.rsplit("/", 1)[-1] if path else payload.id
    return (_SLUG.sub("-", name.lower()).strip("-") or "page")[:40]


def page_link(base_url: str, key: str, slug: str) -> str:
    return f"{base_url.rstrip('/')}/p/{key}/{slug}"


async def create_pages(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    payloads: list[Payload],
    base_url: str,
    ttl: timedelta,
) -> list[Payload]:
    """Host every indirect test's page; return the payloads with their links."""
    now = datetime.now(UTC)
    await db.execute(delete(HostedPage).where(HostedPage.expires_at < now))
    out: list[Payload] = []
    for payload in payloads:
        if payload.track is not Track.INDIRECT or payload.page_html is None:
            out.append(payload)
            continue
        key = secrets.token_urlsafe(24)
        db.add(
            HostedPage(
                link_key=key,
                campaign_id=campaign_id,
                payload_id=payload.id,
                html=payload.page_html,
                expires_at=now + ttl,
            )
        )
        link = page_link(base_url, key, slug_for(payload))
        out.append(replace(payload, page_link=link, hosted_key=key))
    return out


async def record_fetch(db: AsyncSession, key: str, user_agent: str | None) -> HostedPage | None:
    """The page for link ``key`` if it is live, counting this fetch."""
    page = await db.scalar(select(HostedPage).where(HostedPage.link_key == key))
    now = datetime.now(UTC)
    if page is None or _aware(page.expires_at) < now:
        return None
    page.fetch_count += 1
    if page.first_fetched_at is None:
        page.first_fetched_at = now
    page.last_user_agent = (user_agent or "")[:200] or None
    await db.commit()
    return page


async def fetch_status(key: str) -> FetchStatus:
    async with get_sessionmaker()() as db:
        page = await db.scalar(select(HostedPage).where(HostedPage.link_key == key))
    if page is None:
        return FetchStatus(0, None, None)
    return FetchStatus(page.fetch_count, page.first_fetched_at, page.last_user_agent)


def _aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes; they are stored in UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)
