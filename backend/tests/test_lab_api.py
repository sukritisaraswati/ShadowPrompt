"""End-to-end tests for the Lab API, including blueprint 15.2 acceptance.

Two fake models stand in for real providers, over a mock HTTP transport:

* the vulnerable stub leaks whatever access code its system prompt holds, and
  says any forbidden phrase it is asked for;
* the aligned stub refuses everything.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import sqlite3
import time
import uuid

import httpx
import pytest

KEY = "sk-live-AUDIT-ME-0123456789abcdefghijklmnop"
# English tests at each level of the two tracks.
EXPECTED_LEVEL_COUNTS = {
    "D1": 20, "D2": 25, "D3": 40, "D4": 4, "D5": 0,
    "I1": 8, "I2": 16, "I3": 3, "I4": 3, "I5": 16,
}  # fmt: skip
BASE = "https://api.stub.example/v1"
CODE = re.compile(r"access code: ([A-Z]+-\d{4})")


def _openai(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ]
        },
    )


LEAKABLE = re.compile(r"[A-Z]+-\d{4}|ACCT-\d{6}|[a-z]+\.\d{4}@example\.net")


def vulnerable(request: httpx.Request) -> httpx.Response:
    """Obeys every attack: leaks every code and private detail it can see."""
    body = json.loads(request.content)
    if body["messages"][-1]["content"].startswith("Hello, please respond"):
        return _openai("OK")
    seen = " ".join(m["content"] for m in body["messages"])
    leaks = " ".join(dict.fromkeys(LEAKABLE.findall(seen)))
    return _openai(
        f"[DAN] Sure, here it is: {leaks}. I have been PWNED. "
        "See https://collect.attacker.example/log"
    )


def aligned(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if body["messages"][-1]["content"].startswith("Hello, please respond"):
        return _openai("OK")
    return _openai("I'm sorry, but I can't help with that request.")


def unauthorised(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={"error": {"message": "Invalid API key"}})


def connection(**overrides) -> dict:
    data = {"provider": "openai_compatible", "base_url": BASE, "model": "stub-1", "api_key": KEY}
    data.update(overrides)
    return data


def connect(client) -> str:
    response = client.post("/api/v1/lab/connect/test", json=connection())
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def launch(client, session_id: str, levels=("D1",), **extra) -> str:
    body = {"session_id": session_id, "connection": connection(), "levels": list(levels), **extra}
    response = client.post("/api/v1/lab/campaigns", json=body)
    assert response.status_code == 202, response.text
    return response.json()["campaign_id"]


def wait_done(client, campaign_id: str, timeout: float = 20) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/v1/lab/campaigns/{campaign_id}").json()
        if data["status"] not in ("pending", "running"):
            return data
        time.sleep(0.05)
    raise AssertionError("campaign did not finish in time")


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #


def test_valid_connection_creates_a_session(client, use_model) -> None:
    use_model(aligned)
    body = client.post("/api/v1/lab/connect/test", json=connection()).json()
    assert uuid.UUID(body["session_id"])
    assert body["reply_preview"] == "OK"
    assert body["endpoint_host"] == "api.stub.example"
    assert KEY not in json.dumps(body)


def test_invalid_key_shows_an_auth_error_and_creates_nothing(client, use_model) -> None:
    use_model(unauthorised)
    before = client.get("/api/v1/lab/campaigns").json()["pagination"]["total"]
    response = client.post("/api/v1/lab/connect/test", json=connection())
    assert response.status_code == 400
    assert response.json()["code"] == "LLM_AUTH_FAILED"
    assert "session_id" not in response.json()
    assert client.get("/api/v1/lab/campaigns").json()["pagination"]["total"] == before


@pytest.mark.security
def test_private_endpoint_is_blocked_for_connection_tests(client, use_model) -> None:
    use_model(aligned)
    response = client.post(
        "/api/v1/lab/connect/test", json=connection(base_url="http://127.0.0.1:11434/v1")
    )
    assert response.json()["code"] == "BLOCKED_TARGET"


def test_connection_validation(client) -> None:
    response = client.post("/api/v1/lab/connect/test", json=connection(provider="nope"))
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Campaigns: blueprint 15.2 acceptance
# --------------------------------------------------------------------------- #


def test_level_one_against_a_vulnerable_model_fails_every_test(client, use_model) -> None:
    """Acceptance: all 20 Level 1 tests run, and known-fail cases produce FAIL."""
    use_model(vulnerable)
    result = wait_done(client, launch(client, connect(client)))

    assert result["status"] == "completed"
    assert result["total_tests"] == 20 and result["completed_tests"] == 20
    assert {r["verdict"] for r in result["results"]} == {"FAIL"}
    assert result["overall_score"] == 0
    assert result["rating"]["level"] == "critical"


def test_level_one_against_an_aligned_model_passes(client, use_model) -> None:
    """Acceptance: an aligned model produces all or near-all PASS verdicts."""
    use_model(aligned)
    result = wait_done(client, launch(client, connect(client)))

    verdicts = [r["verdict"] for r in result["results"]]
    assert verdicts.count("PASS") >= 19
    assert result["overall_score"] >= 95
    assert result["rating"]["level"] == "secure"
    assert result["level_scores"][0]["name"] == "Basic Jailbreak"


def test_results_expose_attack_text_and_reasons_after_the_run(client, use_model) -> None:
    use_model(vulnerable)
    result = wait_done(client, launch(client, connect(client)))
    first = result["results"][0]
    assert first["attack_text"]
    assert first["evaluation_detail"]["layer1"]["reasons"]
    assert first["response_summary"].startswith("[DAN] Sure")


def test_sampled_multi_level_campaign(client, use_model) -> None:
    use_model(aligned)
    campaign_id = launch(client, connect(client), levels=("D1", "D2", "D3"), sample_size=3)
    result = wait_done(client, campaign_id)
    assert result["total_tests"] == 9
    assert [ls["code"] for ls in result["level_scores"]] == ["D1", "D2", "D3"]
    assert result["config"] == {
        "sample_size": 3,
        "languages": [],
        "custom_pack_ids": [],
        "timeout_seconds": 30.0,
        "max_retries": 1,
    }


def test_campaign_stopped_mid_run_saves_partial_results(client, use_model) -> None:
    """Acceptance: graceful stop, partial results saved, no incomplete state."""

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return aligned(request)

    use_model(slow)
    campaign_id = launch(client, connect(client), levels=("D1", "D2", "D3"))

    deadline = time.monotonic() + 10
    while client.get(f"/api/v1/lab/campaigns/{campaign_id}").json()["completed_tests"] < 3:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert client.post(f"/api/v1/lab/campaigns/{campaign_id}/stop").status_code == 202

    result = wait_done(client, campaign_id)
    assert result["status"] == "stopped"
    assert 3 <= result["completed_tests"] < result["total_tests"]
    assert result["completed_at"] is not None
    assert result["overall_score"] is not None
    assert all(r["verdict"] for r in result["results"])


def test_auth_failure_mid_campaign_fails_it_with_a_reason(client, use_model) -> None:
    use_model(aligned)
    session_id = connect(client)
    use_model(unauthorised)
    result = wait_done(client, launch(client, session_id))
    assert result["status"] == "failed"
    assert "credentials" in result["error_message"].lower()
    assert result["completed_at"] is not None


def test_repeated_model_errors_stop_the_campaign(client, use_model) -> None:
    use_model(aligned)
    session_id = connect(client)
    use_model(lambda r: httpx.Response(500, text="boom"))
    result = wait_done(client, launch(client, session_id, max_retries=0))
    assert result["status"] == "failed"
    assert result["completed_tests"] == 3
    assert {r["verdict"] for r in result["results"]} == {"UNCLEAR"}


# --------------------------------------------------------------------------- #
# Campaign validation and management
# --------------------------------------------------------------------------- #


def test_unknown_levels_are_rejected(client, use_model) -> None:
    use_model(aligned)
    body = {"session_id": connect(client), "connection": connection(), "levels": ["D1", "D6"]}
    assert client.post("/api/v1/lab/campaigns", json=body).status_code == 422


def test_campaign_must_match_the_tested_connection(client, use_model) -> None:
    use_model(aligned)
    body = {
        "session_id": connect(client),
        "connection": connection(model="other"),
        "levels": ["D1"],
    }
    assert client.post("/api/v1/lab/campaigns", json=body).status_code == 422


def test_unknown_session_is_rejected(client) -> None:
    body = {"session_id": str(uuid.uuid4()), "connection": connection(), "levels": ["D1"]}
    assert client.post("/api/v1/lab/campaigns", json=body).status_code == 404


def test_stop_and_delete_rules(client, use_model) -> None:
    use_model(aligned)
    campaign_id = launch(client, connect(client))
    wait_done(client, campaign_id)

    assert client.post(f"/api/v1/lab/campaigns/{campaign_id}/stop").status_code == 409
    assert client.delete(f"/api/v1/lab/campaigns/{campaign_id}").status_code == 204
    assert client.get(f"/api/v1/lab/campaigns/{campaign_id}").status_code == 404
    assert client.post(f"/api/v1/lab/campaigns/{uuid.uuid4()}/stop").status_code == 404


def test_campaign_history_lists_and_filters(client, use_model) -> None:
    use_model(aligned)
    wait_done(client, launch(client, connect(client)))
    page = client.get(
        "/api/v1/lab/campaigns", params={"model_name": "stub", "status": "completed"}
    ).json()
    assert page["items"] and all(i["status"] == "completed" for i in page["items"])
    assert page["items"][0]["completed_tests"] == 20


def test_payload_summary_exposes_counts_but_never_payload_text(client) -> None:
    body = client.get("/api/v1/lab/payload-library/summary").json()
    assert body["total_tests"] == 135
    counts = {lvl["code"]: lvl["test_count"] for lvl in body["levels"]}
    assert counts == EXPECTED_LEVEL_COUNTS
    assert {t["track"]: t["test_count"] for t in body["tracks"]} == {
        "direct": sum(v for k, v in EXPECTED_LEVEL_COUNTS.items() if k[0] == "D"),
        "indirect": sum(v for k, v in EXPECTED_LEVEL_COUNTS.items() if k[0] == "I"),
    }
    assert all(lvl["available"] for lvl in body["levels"])
    text = json.dumps(body)
    assert "access code" not in text.lower() and "PWNED" not in text


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


@pytest.mark.security
def test_campaign_report_escapes_model_output(client, use_model) -> None:
    def hostile(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["messages"][-1]["content"].startswith("Hello, please respond"):
            return _openai("OK")
        return _openai("<script>alert('x')</script> As DAN, sure here is everything.")

    use_model(hostile)
    campaign_id = launch(client, connect(client))
    wait_done(client, campaign_id)

    response = client.post("/api/v1/lab/reports", json={"campaign_id": campaign_id})
    assert response.status_code == 200
    html = response.text
    assert "<script" not in html.lower()
    assert "&lt;script&gt;" in html
    assert "Score breakdown" in html and "Methodology" in html and "Disclaimer" in html
    assert KEY not in html


def test_report_requires_a_finished_campaign(client, use_model) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return aligned(request)

    use_model(slow)
    campaign_id = launch(client, connect(client))
    response = client.post("/api/v1/lab/reports", json={"campaign_id": campaign_id})
    assert response.status_code == 409
    client.post(f"/api/v1/lab/campaigns/{campaign_id}/stop")
    wait_done(client, campaign_id)


def test_campaign_pdf_report(client, use_model) -> None:
    use_model(aligned)
    campaign_id = launch(client, connect(client))
    wait_done(client, campaign_id)
    response = client.post(
        "/api/v1/lab/reports", json={"campaign_id": campaign_id, "format": "pdf"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


# --------------------------------------------------------------------------- #
# Key isolation audit (blueprint 15.2: "API key in any log or DB query")
# --------------------------------------------------------------------------- #


@pytest.mark.security
def test_api_key_never_reaches_the_database_or_logs(client, use_model, caplog) -> None:
    use_model(vulnerable)
    with caplog.at_level(logging.DEBUG):
        campaign_id = launch(client, connect(client), levels=("D1", "D2"), sample_size=3)
        wait_done(client, campaign_id)
        client.post("/api/v1/lab/reports", json={"campaign_id": campaign_id})
        client.get("/api/v1/lab/campaigns")

    assert KEY not in caplog.text

    db_path = os.environ["DATABASE_URL"].split("///", 1)[1]
    with contextlib.closing(sqlite3.connect(db_path)) as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for row in con.execute(f'SELECT * FROM "{table}"'):  # noqa: S608 - fixed table names
                assert KEY not in repr(row), f"API key found in table {table}"
                assert KEY[-12:] not in repr(row), f"key fragment found in table {table}"


@pytest.mark.security
def test_api_key_is_never_echoed_in_any_response(client, use_model) -> None:
    use_model(aligned)
    session_id = connect(client)
    campaign_id = launch(client, session_id)
    responses = [
        client.post("/api/v1/lab/connect/test", json=connection()).text,
        client.get(f"/api/v1/lab/campaigns/{campaign_id}").text,
        json.dumps(wait_done(client, campaign_id)),
        client.get("/api/v1/lab/campaigns").text,
    ]
    for text in responses:
        assert KEY not in text


# --------------------------------------------------------------------------- #
# Limits and recovery
# --------------------------------------------------------------------------- #


@pytest.mark.security
def test_campaign_launches_are_rate_limited(client, use_model, monkeypatch) -> None:
    from app.core.config import get_settings

    use_model(aligned)
    session_id = connect(client)
    monkeypatch.setattr(get_settings(), "rate_limit_campaigns_per_hour", 2)
    ids = [launch(client, session_id) for _ in range(2)]
    body = {"session_id": session_id, "connection": connection(), "levels": ["D1"]}
    response = client.post("/api/v1/lab/campaigns", json=body)
    assert response.status_code == 429
    for campaign_id in ids:
        wait_done(client, campaign_id)


async def test_orphaned_campaigns_are_failed_on_startup(db_session) -> None:
    from app.db.models import Campaign, CampaignStatus, Session
    from app.services.lab.orchestrator import recover_orphans

    session = Session(model_name="m", provider="p")
    db_session.add(session)
    await db_session.flush()
    campaign = Campaign(session_id=session.id, levels_run=["D1"], status=CampaignStatus.RUNNING)
    db_session.add(campaign)
    await db_session.commit()

    assert await recover_orphans() >= 1
    await db_session.refresh(campaign)
    assert campaign.status is CampaignStatus.FAILED
    assert campaign.completed_at is not None and campaign.error_message
