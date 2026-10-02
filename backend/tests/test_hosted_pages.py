"""Phase 5.4: indirect tests delivered as hosted pages a chatbot fetches."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update

from tests.test_chatbot_targets import CANARY, TOKEN, connection
from tests.test_lab_api import wait_done

BASE = "http://testserver"
LINK = re.compile(r"http://testserver/p/[A-Za-z0-9_-]+/[a-z0-9-]+")
PLANTED = re.compile(r"\b[A-Z]{3,}-\d{4}\b")
ATTACKER = re.compile(r"https://[a-z.]*attacker\.example[^\s\"<]*")


@pytest.fixture
def public_base(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.core.config import get_settings

    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("PUBLIC_BASE_URL")
    get_settings.cache_clear()


class BrowsingBot:
    """A chatbot that follows links in the message, as a browsing agent would."""

    def __init__(self, browses: bool, vulnerable: bool) -> None:
        self.browses = browses
        self.vulnerable = vulnerable
        self.pages: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        message = body["message"]
        if message.startswith("Hello, please respond"):
            return httpx.Response(200, json={"reply": "OK"})
        page = ""
        links = LINK.findall(message)
        if self.browses and links:
            from app.main import app

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=BASE
            ) as browser:
                fetched = await browser.get(links[0].removeprefix(BASE))
            page = fetched.text
            self.pages.append(page)
        if self.vulnerable and page:
            evidence = PLANTED.findall(page) + ATTACKER.findall(page)
            planted = " ".join(dict.fromkeys(evidence))
            return httpx.Response(200, json={"reply": f"Done as the page asked. {planted}"})
        return httpx.Response(
            200, json={"reply": "That page describes its topic in a couple of paragraphs."}
        )


def run(client, levels, *, delivery="hosted", sample=2) -> dict:
    conn = connection()
    session = client.post("/api/v1/lab/connect/test", json=conn).json()["session_id"]
    response = client.post(
        "/api/v1/lab/campaigns",
        json={
            "session_id": session,
            "connection": conn,
            "levels": levels,
            "sample_size": sample,
            "indirect_delivery": delivery,
        },
    )
    assert response.status_code == 202, response.text
    return wait_done(client, response.json()["campaign_id"], timeout=60)


def test_capabilities_report_hosted_pages(client, public_base) -> None:
    assert client.get("/api/v1/lab/capabilities").json()["hosted_pages_available"] is True


def test_the_bot_gets_a_link_and_the_fetch_is_recorded(client, use_model, public_base) -> None:
    bot = BrowsingBot(browses=True, vulnerable=False)
    use_model(bot)
    result = run(client, ["I1"])
    assert result["config"]["target"]["indirect_delivery"] == "hosted"
    for r in result["results"]:
        hosted = r["evaluation_detail"]["hosted_page"]
        assert hosted["fetched"] is True and hosted["fetch_count"] == 1
        assert hosted["user_agent"]
        assert LINK.fullmatch(hosted["url"])
        assert hosted["url"] in r["attack_text"]
        assert "<!--" not in r["attack_text"]  # the page itself is not pasted
        assert r["verdict"] == "PASS"
    assert len(bot.pages) == 2 and all("<html" in p.lower() for p in bot.pages)


def test_a_bot_that_obeys_the_fetched_page_fails(client, use_model, public_base) -> None:
    use_model(BrowsingBot(browses=True, vulnerable=True))
    result = run(client, ["I1"])
    assert {r["verdict"] for r in result["results"]} == {"FAIL"}


def test_a_bot_that_never_fetches_is_unclear_not_passed(client, use_model, public_base) -> None:
    use_model(BrowsingBot(browses=False, vulnerable=False))
    result = run(client, ["I1"])
    for r in result["results"]:
        assert r["verdict"] == "UNCLEAR"
        assert r["evaluation_detail"]["decided_by"] == "page_not_fetched"
        assert r["evaluation_detail"]["hosted_page"]["fetched"] is False


def test_direct_tests_are_unaffected_by_hosted_delivery(client, use_model, public_base) -> None:
    use_model(BrowsingBot(browses=True, vulnerable=False))
    result = run(client, ["D2"])
    assert all("hosted_page" not in r["evaluation_detail"] for r in result["results"])


@pytest.mark.security
def test_hosted_pages_are_served_defensively(client, use_model, public_base) -> None:
    bot = BrowsingBot(browses=False, vulnerable=False)
    use_model(bot)
    result = run(client, ["I1"], sample=1)
    url = result["results"][0]["evaluation_detail"]["hosted_page"]["url"]
    page = client.get(url.removeprefix(BASE))
    assert page.status_code == 200
    csp = page.headers["content-security-policy"]
    assert csp.startswith("sandbox") and "script-src" not in csp
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"


@pytest.mark.security
@pytest.mark.parametrize("path", ["/p/not-a-real-key/page", "/p/" + "a" * 80 + "/x", "/p/x"])
def test_unknown_links_are_not_found(client, path) -> None:
    assert client.get(path).status_code == 404


@pytest.mark.security
async def test_expired_pages_are_not_served(client, use_model, public_base, db_session) -> None:
    from app.db.models import HostedPage

    use_model(BrowsingBot(browses=False, vulnerable=False))
    result = run(client, ["I1"], sample=1)
    url = result["results"][0]["evaluation_detail"]["hosted_page"]["url"]
    key = url.split("/")[-2]
    await db_session.execute(
        update(HostedPage)
        .where(HostedPage.link_key == key)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    assert client.get(url.removeprefix(BASE)).status_code == 404


def test_hosted_delivery_needs_a_chatbot_and_a_public_address(client, use_model) -> None:
    use_model(BrowsingBot(browses=True, vulnerable=False))
    conn = connection()
    session = client.post("/api/v1/lab/connect/test", json=conn).json()["session_id"]
    body = {
        "session_id": session,
        "connection": conn,
        "levels": ["I1"],
        "indirect_delivery": "hosted",
    }
    response = client.post("/api/v1/lab/campaigns", json=body)
    assert response.status_code == 422
    assert "PUBLIC_BASE_URL" in response.json()["detail"]


def test_hosted_delivery_is_refused_for_model_apis(client, use_model, public_base) -> None:
    from tests.test_lab_api import aligned
    from tests.test_lab_api import connection as model_connection

    use_model(aligned)
    session = client.post("/api/v1/lab/connect/test", json=model_connection()).json()
    body = {
        "session_id": session["session_id"],
        "connection": model_connection(),
        "levels": ["I1"],
        "indirect_delivery": "hosted",
    }
    response = client.post("/api/v1/lab/campaigns", json=body)
    assert response.status_code == 422
    assert "model API" in response.json()["message"]


def test_fixture_values_line_up() -> None:
    # The shared chatbot fixtures this module relies on.
    assert CANARY and TOKEN.startswith("Bearer ")
