"""Tests for the provider-agnostic LLM client."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import AppError
from app.services.lab.llm_client import (
    ChatMessage,
    LlmBackend,
    LlmConfig,
    Provider,
    build_request,
    chat,
    parse_reply,
)

KEY = "sk-test-SUPERSECRETKEY0123456789abcdef"
PUBLIC_IP = "93.184.216.34"
MESSAGES = [ChatMessage("system", "Be helpful."), ChatMessage("user", "Hello")]


def cfg(provider: Provider = Provider.OPENAI_COMPATIBLE, **kw) -> LlmConfig:
    base = {
        Provider.OPENAI_COMPATIBLE: "https://api.test.example/v1",
        Provider.ANTHROPIC: "https://api.test.example",
        Provider.GEMINI: "https://api.test.example",
        Provider.AZURE_OPENAI: "https://api.test.example/openai/deployments/gpt4o",
    }[provider]
    values = dict(
        provider=provider,
        base_url=base,
        model="test-model",
        api_key=SecretStr(KEY),
        timeout_seconds=5,
        max_retries=0,
    )
    values.update(kw)
    return LlmConfig(**values)


def openai_body(text: str, finish: str = "stop") -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}]
    }


async def no_sleep(_seconds: float) -> None:
    return None


def backend(handler, dns: dict[str, list[str]] | None = None) -> LlmBackend:
    table = dns or {"api.test.example": [PUBLIC_IP]}

    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("unknown host")
        return table[host]

    return LlmBackend(transport=httpx.MockTransport(handler), resolver=resolve, sleep=no_sleep)


def settings(**kw) -> Settings:
    return Settings(llm_retry_base_delay=0, **kw)


# --------------------------------------------------------------------------- #
# Wire formats
# --------------------------------------------------------------------------- #


def test_openai_request_shape() -> None:
    wire = build_request(cfg(), MESSAGES, 400)
    assert wire.url == "https://api.test.example/v1/chat/completions"
    assert wire.headers["Authorization"] == f"Bearer {KEY}"
    assert wire.body["model"] == "test-model"
    assert wire.body["messages"][0] == {"role": "system", "content": "Be helpful."}
    assert wire.body["max_tokens"] == 400


def test_openai_base_url_may_already_include_the_path() -> None:
    wire = build_request(
        cfg(base_url="https://api.test.example/v1/chat/completions/"), MESSAGES, 10
    )
    assert wire.url == "https://api.test.example/v1/chat/completions"


def test_anthropic_request_shape() -> None:
    wire = build_request(cfg(Provider.ANTHROPIC), MESSAGES, 400)
    assert wire.url == "https://api.test.example/v1/messages"
    assert wire.headers["x-api-key"] == KEY
    assert "anthropic-version" in wire.headers
    assert wire.body["system"] == "Be helpful."
    assert all(m["role"] != "system" for m in wire.body["messages"])


def test_gemini_request_shape_keeps_the_key_out_of_the_url() -> None:
    wire = build_request(cfg(Provider.GEMINI), MESSAGES, 400)
    assert wire.url.endswith("/v1beta/models/test-model:generateContent")
    assert KEY not in wire.url
    assert wire.headers["x-goog-api-key"] == KEY
    assert wire.body["systemInstruction"]["parts"][0]["text"] == "Be helpful."


def test_azure_request_shape() -> None:
    wire = build_request(cfg(Provider.AZURE_OPENAI), MESSAGES, 400)
    assert wire.url.startswith(
        "https://api.test.example/openai/deployments/gpt4o/chat/completions?api-version="
    )
    assert wire.headers["api-key"] == KEY
    assert "model" not in wire.body


def test_no_key_means_no_auth_header() -> None:
    wire = build_request(cfg(api_key=None), MESSAGES, 10)
    assert "Authorization" not in wire.headers


@pytest.mark.parametrize(
    ("provider", "data", "text", "blocked"),
    [
        (Provider.OPENAI_COMPATIBLE, openai_body("hi"), "hi", False),
        (Provider.OPENAI_COMPATIBLE, openai_body("", "content_filter"), "", True),
        (Provider.OPENAI_COMPATIBLE, {"choices": [{"message": {"refusal": "No."}}]}, "No.", True),
        (
            Provider.ANTHROPIC,
            {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
            "ab",
            False,
        ),
        (Provider.GEMINI, {"candidates": [{"content": {"parts": [{"text": "g"}]}}]}, "g", False),
        (Provider.GEMINI, {"promptFeedback": {"blockReason": "SAFETY"}}, "", True),
        (Provider.GEMINI, {"candidates": [{"finishReason": "SAFETY"}]}, "", True),
    ],
)
def test_reply_parsing(provider, data, text, blocked) -> None:
    assert parse_reply(provider, data) == (text, blocked)


def test_config_repr_never_shows_the_key() -> None:
    assert KEY not in repr(cfg())
    assert KEY not in str(cfg())


# --------------------------------------------------------------------------- #
# Calling
# --------------------------------------------------------------------------- #


async def test_successful_call_is_pinned_and_returns_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=openai_body("OK"))

    reply = await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert reply.text == "OK"
    assert seen[0].url.host == PUBLIC_IP
    assert seen[0].headers["host"] == "api.test.example"
    assert json.loads(seen[0].content)["model"] == "test-model"


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "LLM_AUTH_FAILED"), (403, "LLM_AUTH_FAILED"), (404, "LLM_MODEL_NOT_FOUND")],
)
async def test_client_errors_map_to_specific_codes(status: int, code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": f"bad thing, key {KEY}"}})

    with pytest.raises(AppError) as info:
        await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert info.value.code == code
    assert KEY not in (info.value.detail or "")
    assert KEY not in info.value.message


async def test_masked_key_fragments_are_scrubbed_from_error_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "Incorrect API key provided: sk-proj-****wxyz."}}
        )

    with pytest.raises(AppError) as info:
        await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert "wxyz" not in (info.value.detail or "")


async def test_rate_limit_is_retried_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=openai_body("ok"))

    reply = await chat(cfg(max_retries=2), MESSAGES, settings=settings(), backend=backend(handler))
    assert reply.text == "ok" and reply.attempts == 2


async def test_rate_limit_exhausts_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    with pytest.raises(AppError) as info:
        await chat(cfg(max_retries=1), MESSAGES, settings=settings(), backend=backend(handler))
    assert info.value.code == "LLM_RATE_LIMITED"


async def test_server_error_is_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls < 3 else httpx.Response(200, json=openai_body("up"))

    reply = await chat(cfg(max_retries=3), MESSAGES, settings=settings(), backend=backend(handler))
    assert reply.attempts == 3


async def test_timeout_maps_to_llm_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AppError) as info:
        await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert info.value.code == "LLM_TIMEOUT"


async def test_connection_failure_maps_to_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AppError) as info:
        await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert info.value.code == "LLM_UNREACHABLE"


async def test_unknown_host_maps_to_unreachable() -> None:
    with pytest.raises(AppError) as info:
        await chat(
            cfg(base_url="https://nowhere.example/v1"),
            MESSAGES,
            settings=settings(),
            backend=backend(lambda r: httpx.Response(200)),
        )
    assert info.value.code == "LLM_UNREACHABLE"


async def test_unsupported_sampling_parameters_fall_back() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "max_tokens" in body:
            return httpx.Response(
                400, json={"error": {"message": "Unsupported parameter: 'max_tokens'"}}
            )
        return httpx.Response(200, json=openai_body("fine"))

    reply = await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert reply.text == "fine"
    assert "max_completion_tokens" in bodies[1] and "temperature" not in bodies[1]


async def test_content_filter_400_counts_as_provider_block() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"code": "content_filter", "message": "filtered"}}
        )

    reply = await chat(
        cfg(Provider.AZURE_OPENAI), MESSAGES, settings=settings(), backend=backend(handler)
    )
    assert reply.provider_blocked is True


async def test_oversized_response_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000)

    with pytest.raises(AppError) as info:
        await chat(
            cfg(),
            MESSAGES,
            settings=settings(llm_max_response_bytes=1000),
            backend=backend(handler),
        )
    assert info.value.code == "LLM_UNREACHABLE"


async def test_malformed_response_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(AppError) as info:
        await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert info.value.code == "LLM_UNREACHABLE"


# --------------------------------------------------------------------------- #
# Endpoint safety
# --------------------------------------------------------------------------- #


def never(request: httpx.Request) -> httpx.Response:
    raise AssertionError("a blocked endpoint must never be contacted")


@pytest.mark.security
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:8000/v1",
        "http://10.0.0.5/v1",
        "http://169.254.169.254/latest",
        "http://[::1]:8080/v1",
    ],
)
async def test_private_endpoints_are_blocked_by_default(url: str) -> None:
    with pytest.raises(AppError) as info:
        await chat(cfg(base_url=url), MESSAGES, settings=settings(), backend=backend(never))
    assert info.value.code == "BLOCKED_TARGET"


@pytest.mark.security
async def test_private_endpoints_can_be_enabled_for_self_hosting() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openai_body("local ok"))

    reply = await chat(
        cfg(base_url="http://127.0.0.1:11434/v1", api_key=None),
        MESSAGES,
        settings=settings(llm_allow_private_endpoints=True),
        backend=backend(handler),
    )
    assert reply.text == "local ok"


@pytest.mark.security
async def test_metadata_endpoint_stays_blocked_even_when_private_is_allowed() -> None:
    with pytest.raises(AppError) as info:
        await chat(
            cfg(base_url="http://169.254.169.254/v1"),
            MESSAGES,
            settings=settings(llm_allow_private_endpoints=True),
            backend=backend(never),
        )
    assert info.value.code == "BLOCKED_TARGET"


@pytest.mark.security
async def test_key_never_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": f"bad key {KEY}"}})

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AppError):
            await chat(cfg(), MESSAGES, settings=settings(), backend=backend(handler))
    assert KEY not in caplog.text
