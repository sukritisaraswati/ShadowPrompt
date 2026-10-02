"""Provider-agnostic LLM client for the Lab (blueprint 3.1 and 10.3).

One ``chat`` call takes a list of messages, sends it to the user's model, and
returns the reply text. Four wire formats are supported:

* ``openai_compatible``: OpenAI, Groq, Together, Fireworks, OpenRouter, vLLM,
  LM Studio, Ollama and anything else speaking ``/chat/completions``.
* ``anthropic``: the Anthropic Messages API.
* ``gemini``: the Google Gemini ``generateContent`` API.
* ``azure_openai``: an Azure OpenAI deployment URL.

Security properties:

* Every request goes through :mod:`app.core.netguard`, so the proxy cannot be
  pointed at internal services.
* The API key travels only in a request header, never in a URL, because URLs
  end up in logs. It is held in a :class:`pydantic.SecretStr` so it cannot
  leak through ``repr`` or a log line, and it is scrubbed from any provider
  error text before that text reaches the caller.
* Replies are size-capped while streaming and treated strictly as text.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import redact
from app.core.netguard import Resolver, parse_target, pin, resolve_public, system_resolver
from app.schemas.common import ErrorCode

AZURE_API_VERSION = "2024-10-21"
ANTHROPIC_VERSION = "2023-06-01"
_KEYISH = re.compile(r"\b(?:sk|key|pk|rk)-[\w*.\-]{4,}", re.I)


class Provider(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    AZURE_OPENAI = "azure_openai"


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LlmConfig:
    provider: Provider
    base_url: str
    model: str
    api_key: SecretStr | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 1

    def __repr__(self) -> str:  # never show the key, even masked
        return (
            f"LlmConfig(provider={self.provider}, base_url={self.base_url!r}, model={self.model!r})"
        )


@dataclass(frozen=True)
class LlmReply:
    text: str
    latency_ms: int
    # True when the provider itself refused to generate (content filter or
    # safety block). That is a successful defence, not a transport error.
    provider_blocked: bool = False
    attempts: int = 1


@dataclass
class LlmBackend:
    """Transport and DNS used for model calls. Replaced in tests."""

    transport: httpx.AsyncBaseTransport | None = None
    resolver: Resolver = system_resolver
    sleep: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)


# --------------------------------------------------------------------------- #
# Wire formats
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _WireRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


def _key(config: LlmConfig) -> str | None:
    return config.api_key.get_secret_value() if config.api_key else None


def _split_system(messages: Sequence[ChatMessage]) -> tuple[str, list[ChatMessage]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    return system, [m for m in messages if m.role != "system"]


def _openai_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def build_request(
    config: LlmConfig, messages: Sequence[ChatMessage], max_tokens: int, *, compat: bool = False
) -> _WireRequest:
    """The provider-specific URL, headers and JSON body for one call.

    ``compat`` retries an OpenAI-style call without sampling parameters, for
    newer models that reject ``max_tokens`` or a non-default temperature.
    """
    key = _key(config)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    if config.provider is Provider.ANTHROPIC:
        system, turns = _split_system(messages)
        if key:
            headers["x-api-key"] = key
        headers["anthropic-version"] = ANTHROPIC_VERSION
        body: dict[str, Any] = {
            "model": config.model,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in turns],
        }
        if system:
            body["system"] = system
        base = config.base_url.rstrip("/")
        url = base if base.endswith("/messages") else base + "/v1/messages"
        return _WireRequest(url, headers, body)

    if config.provider is Provider.GEMINI:
        system, turns = _split_system(messages)
        if key:
            headers["x-goog-api-key"] = key
        body = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in turns
            ],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        base = config.base_url.rstrip("/")
        url = f"{base}/v1beta/models/{config.model}:generateContent"
        return _WireRequest(url, headers, body)

    body = {"messages": [{"role": m.role, "content": m.content} for m in messages]}
    if compat:
        body["max_completion_tokens"] = max_tokens
    else:
        body["max_tokens"] = max_tokens
        body["temperature"] = 0

    if config.provider is Provider.AZURE_OPENAI:
        if key:
            headers["api-key"] = key
        url = f"{_openai_url(config.base_url)}?api-version={AZURE_API_VERSION}"
        return _WireRequest(url, headers, body)

    if key:
        headers["Authorization"] = f"Bearer {key}"
    body["model"] = config.model
    return _WireRequest(_openai_url(config.base_url), headers, body)


def parse_reply(provider: Provider, data: Any) -> tuple[str, bool]:
    """Extract ``(text, provider_blocked)`` from a provider response body."""
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")

    if provider is Provider.ANTHROPIC:
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return text, data.get("stop_reason") == "refusal"

    if provider is Provider.GEMINI:
        if (data.get("promptFeedback") or {}).get("blockReason"):
            return "", True
        candidates = data.get("candidates") or []
        if not candidates:
            return "", True
        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        blocked = candidate.get("finishReason") in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"}
        return text, blocked and not text

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("response has no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # some servers return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    text = content or message.get("refusal") or ""
    blocked = choice.get("finish_reason") == "content_filter" or bool(message.get("refusal"))
    return text, blocked


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


def _scrub(text: str, config: LlmConfig) -> str:
    """Make provider error text safe to show: no key, no key fragments."""
    key = _key(config)
    if key:
        text = text.replace(key, "[REDACTED]")
    text = _KEYISH.sub("[REDACTED]", redact(text))
    return text[:300]


def _provider_message(raw: bytes) -> str:
    try:
        data = json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")[:300]
    if isinstance(data, dict):
        error = data.get("error", data)
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)[:300]
        if isinstance(error, str):
            return error[:300]
    return str(data)[:300]


class _Retryable(Exception):
    def __init__(self, error: AppError, retry_after: float | None = None) -> None:
        super().__init__(error.message)
        self.error = error
        self.retry_after = retry_after


def _status_error(status: int, raw: bytes, config: LlmConfig) -> AppError:
    detail = _scrub(_provider_message(raw), config)
    if status in (401, 403):
        return AppError(
            ErrorCode.LLM_AUTH_FAILED,
            "The model provider rejected the credentials. Check the API key.",
            status_code=400,
            detail=detail,
        )
    if status == 404:
        return AppError(
            ErrorCode.LLM_MODEL_NOT_FOUND,
            "The endpoint or model was not found. Check the base URL and model name.",
            status_code=400,
            detail=detail,
        )
    if status == 429:
        return AppError(
            ErrorCode.LLM_RATE_LIMITED,
            "The model provider is rate limiting requests.",
            status_code=429,
            detail=detail,
        )
    return AppError(
        ErrorCode.LLM_UNREACHABLE,
        f"The model provider returned HTTP {status}.",
        status_code=502,
        detail=detail,
    )


def _needs_compat(status: int, raw: bytes) -> bool:
    if status != 400:
        return False
    text = raw.decode("utf-8", "replace").lower()
    return any(word in text for word in ("max_tokens", "temperature", "max_completion_tokens"))


async def _read_capped(response: httpx.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise AppError(
                ErrorCode.LLM_UNREACHABLE,
                "The model's response exceeded the size limit.",
                status_code=502,
            )
        chunks.append(chunk)
    return b"".join(chunks)


# --------------------------------------------------------------------------- #
# Calling
# --------------------------------------------------------------------------- #


async def _attempt(
    client: httpx.AsyncClient,
    config: LlmConfig,
    messages: Sequence[ChatMessage],
    settings: Settings,
    backend: LlmBackend,
    compat: bool,
) -> tuple[str, bool]:
    wire = build_request(config, messages, settings.llm_max_output_tokens, compat=compat)
    allow_private = settings.llm_allow_private_endpoints
    target = parse_target(wire.url, allow_private=allow_private)
    try:
        address = await resolve_public(target, backend.resolver, allow_private=allow_private)
    except AppError as exc:
        if exc.code != ErrorCode.FETCH_FAILED:
            raise
        raise AppError(
            ErrorCode.LLM_UNREACHABLE,
            "The model host name could not be resolved. Check the base URL.",
            status_code=502,
            detail=target.host,
        ) from exc
    pinned = pin(target, address)
    headers = {**wire.headers, "Host": pinned.host_header}

    async with client.stream(
        "POST", pinned.url, headers=headers, json=wire.body, extensions=pinned.extensions
    ) as response:
        raw = await _read_capped(response, settings.llm_max_response_bytes)
        status = response.status_code

    if status >= 400:
        if not compat and config.provider in (Provider.OPENAI_COMPATIBLE, Provider.AZURE_OPENAI):
            if _needs_compat(status, raw):
                return await _attempt(client, config, messages, settings, backend, True)
        # Azure and OpenAI report a content-filter refusal as a 400.
        if status == 400 and b"content_filter" in raw:
            return "", True
        error = _status_error(status, raw, config)
        if status == 429 or status >= 500:
            retry_after = response.headers.get("retry-after")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else None
            raise _Retryable(error, delay)
        raise error

    try:
        return parse_reply(config.provider, json.loads(raw))
    except ValueError as exc:
        raise AppError(
            ErrorCode.LLM_UNREACHABLE,
            "The model's response was not in the expected format.",
            status_code=502,
            detail="Check that the provider type matches the endpoint.",
        ) from exc


async def chat(
    config: LlmConfig,
    messages: Sequence[ChatMessage],
    *,
    settings: Settings | None = None,
    backend: LlmBackend | None = None,
) -> LlmReply:
    """Send one conversation to the model and return its reply.

    Rate limits, server errors, timeouts and connection failures are retried
    up to ``config.max_retries`` times with exponential backoff. Everything
    else fails immediately with a specific error code.
    """
    settings = settings or get_settings()
    backend = backend or LlmBackend()
    attempts = 0
    started = time.perf_counter()

    async with httpx.AsyncClient(
        transport=backend.transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(config.timeout_seconds),
    ) as client:
        while True:
            attempts += 1
            try:
                async with asyncio.timeout(config.timeout_seconds):
                    text, blocked = await _attempt(
                        client, config, messages, settings, backend, False
                    )
                return LlmReply(
                    text=text,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    provider_blocked=blocked,
                    attempts=attempts,
                )
            except _Retryable as retry:
                failure, wait = retry.error, retry.retry_after
            except (TimeoutError, httpx.TimeoutException):
                failure = AppError(
                    ErrorCode.LLM_TIMEOUT,
                    f"The model did not respond within {config.timeout_seconds:g} seconds.",
                    status_code=504,
                )
                wait = None
            except httpx.HTTPError as exc:
                failure = AppError(
                    ErrorCode.LLM_UNREACHABLE,
                    "The model endpoint could not be reached.",
                    status_code=502,
                    detail=type(exc).__name__,
                )
                wait = None

            if attempts > config.max_retries:
                raise failure
            delay = (
                wait if wait is not None else settings.llm_retry_base_delay * 2 ** (attempts - 1)
            )
            await backend.sleep(min(delay, 10.0))
