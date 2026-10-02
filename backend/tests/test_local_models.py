"""Phase 4.1: local models, allowed only behind the self-hosting flag."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest

from app.services.lab.llm_client import LOCAL_MODELS_HINT
from tests.test_lab_api import _openai, wait_done

LOCAL_SERVERS = {
    "ollama": "http://localhost:11434/v1",
    "lm_studio": "http://localhost:1234/v1",
    "llama_cpp": "http://127.0.0.1:8080/v1",
}


@pytest.fixture
def self_hosted(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run with LLM_ALLOW_PRIVATE_ENDPOINTS=true, as a self-hosted deployment would."""
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_ALLOW_PRIVATE_ENDPOINTS", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("LLM_ALLOW_PRIVATE_ENDPOINTS")
    get_settings.cache_clear()


def local(base_url: str, model: str = "llama3.2") -> dict:
    return {"provider": "openai_compatible", "base_url": base_url, "model": model, "api_key": None}


class Recorder:
    """A local model that records the headers it receives."""

    def __init__(self) -> None:
        self.headers: list[httpx.Headers] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.headers.append(request.headers)
        body = json.loads(request.content)
        if body["messages"][-1]["content"].startswith("Hello, please respond"):
            return _openai("OK")
        return _openai("I'm sorry, but I can't help with that request.")


# --------------------------------------------------------------------------- #
# Default: hosted deployments refuse local endpoints
# --------------------------------------------------------------------------- #


def test_capabilities_report_local_endpoints_off_by_default(client) -> None:
    body = client.get("/api/v1/lab/capabilities").json()
    assert body == {"local_endpoints_allowed": False, "judge_enabled": False}


@pytest.mark.security
@pytest.mark.parametrize("server", list(LOCAL_SERVERS))
def test_local_servers_are_rejected_without_the_flag(client, use_model, server: str) -> None:
    model = Recorder()
    use_model(model)
    response = client.post("/api/v1/lab/connect/test", json=local(LOCAL_SERVERS[server]))
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "BLOCKED_TARGET"
    assert body["message"] == LOCAL_MODELS_HINT
    assert "LLM_ALLOW_PRIVATE_ENDPOINTS=true" in body["message"]
    assert model.headers == []  # nothing was sent


@pytest.mark.security
@pytest.mark.parametrize(
    "url", ["http://10.0.0.5:11434/v1", "http://192.168.1.20:1234/v1", "http://[::1]:8080/v1"]
)
def test_private_network_models_are_rejected_without_the_flag(client, use_model, url: str) -> None:
    use_model(Recorder())
    body = client.post("/api/v1/lab/connect/test", json=local(url)).json()
    assert body["code"] == "BLOCKED_TARGET"
    assert body["message"] == LOCAL_MODELS_HINT


# --------------------------------------------------------------------------- #
# Self-hosted: the flag opens local endpoints, and nothing else
# --------------------------------------------------------------------------- #


def test_capabilities_report_local_endpoints_when_self_hosted(client, self_hosted) -> None:
    assert client.get("/api/v1/lab/capabilities").json()["local_endpoints_allowed"] is True


@pytest.mark.parametrize("server", list(LOCAL_SERVERS))
def test_local_servers_connect_without_a_key_when_self_hosted(
    client, use_model, self_hosted, server: str
) -> None:
    model = Recorder()
    use_model(model)
    response = client.post("/api/v1/lab/connect/test", json=local(LOCAL_SERVERS[server]))
    assert response.status_code == 200, response.text
    assert response.json()["reply_preview"] == "OK"
    # Headerless: a local server gets no Authorization header at all.
    assert all("authorization" not in headers for headers in model.headers)


def test_a_campaign_runs_against_a_local_model(client, use_model, self_hosted) -> None:
    use_model(Recorder())
    connection = local(LOCAL_SERVERS["ollama"])
    session = client.post("/api/v1/lab/connect/test", json=connection).json()["session_id"]
    started = client.post(
        "/api/v1/lab/campaigns",
        json={"session_id": session, "connection": connection, "levels": ["D1"], "sample_size": 3},
    )
    assert started.status_code == 202
    result = wait_done(client, started.json()["campaign_id"])
    assert result["status"] == "completed"
    assert result["session"]["endpoint_host"] == "localhost"
    assert {r["verdict"] for r in result["results"]} == {"PASS"}


@pytest.mark.security
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[fd00:ec2::254]/v1",
        "http://[::ffff:169.254.169.254]/v1",
    ],
)
def test_cloud_metadata_stays_blocked_when_self_hosted(
    client, use_model, self_hosted, url: str
) -> None:
    model = Recorder()
    use_model(model)
    body = client.post("/api/v1/lab/connect/test", json=local(url)).json()
    assert body["code"] == "BLOCKED_TARGET"
    assert body["message"] != LOCAL_MODELS_HINT
    assert model.headers == []


@pytest.mark.security
def test_non_http_schemes_stay_blocked_when_self_hosted(client, use_model, self_hosted) -> None:
    use_model(Recorder())
    response = client.post("/api/v1/lab/connect/test", json=local("file:///etc/passwd"))
    assert response.status_code in (400, 422)
    assert response.json()["code"] in ("BLOCKED_TARGET", "VALIDATION_ERROR")


@pytest.mark.security
@pytest.mark.parametrize("url", ["http://localhost:11434/", "http://127.0.0.1:8080/"])
def test_shadowscan_never_fetches_local_addresses_even_when_self_hosted(
    client, self_hosted, url: str
) -> None:
    """The flag is for the Lab's model proxy only. The page fetcher ignores it."""
    response = client.post("/api/v1/scan/url", json={"url": url})
    assert response.status_code == 400
    assert response.json()["code"] == "BLOCKED_TARGET"
