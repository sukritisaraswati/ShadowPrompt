"""
ShadowPrompt Lab — LLM Connection Proxy
Proxies requests to OpenAI-compatible LLM endpoints.
API keys pass through memory only — never logged or persisted.
Reuses the SSRF blocklist from the scanner fetcher.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings, BLOCKED_NETWORKS
from app.scanner.fetcher import validate_url_scheme, resolve_and_validate, FetchError


# --- Data Models ---

@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    content: str                     # The assistant's response text
    model: str                       # Model that generated the response
    finish_reason: str               # "stop", "length", "content_filter", etc.
    usage: dict = field(default_factory=dict)  # token counts
    latency_ms: float = 0.0         # Round-trip time in milliseconds
    error: Optional[str] = None     # Error message if request failed
    error_code: Optional[str] = None  # Error classification


class LLMProxyError(Exception):
    """Custom exception for LLM proxy errors."""
    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


# --- Constants ---

LLM_TIMEOUT = 60  # Generous timeout for LLM responses (some models are slow)
CONNECTION_TEST_TIMEOUT = 15


# --- Core Functions ---

def _normalize_base_url(base_url: str) -> str:
    """Normalize base URL — ensure it ends correctly for /chat/completions."""
    base_url = base_url.strip().rstrip("/")
    # If user provides full path, strip /chat/completions so we can re-add it
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    if base_url.endswith("/v1"):
        pass  # Already correct
    elif not base_url.endswith("/v1"):
        # Check if it's a known provider that needs /v1
        if "openai.com" in base_url or "groq.com" in base_url or "together.xyz" in base_url:
            base_url += "/v1"
        # Ollama's OpenAI-compatible endpoint is at /v1
        elif "localhost" in base_url or "127.0.0.1" in base_url:
            base_url += "/v1"
    return base_url


def _is_local_endpoint(hostname: str, port: int) -> bool:
    """Check if the target is a permitted local LLM endpoint."""
    if not settings.ALLOW_LOCAL_LLM:
        return False
    if hostname not in ("localhost", "127.0.0.1", "::1"):
        return False
    if port not in settings.LOCAL_LLM_ALLOWED_PORTS:
        return False
    return True


async def _validate_llm_target(base_url: str) -> None:
    """
    Validate the LLM endpoint URL against SSRF rules.
    Uses the same blocklist as the scanner fetcher, with an exception
    for local LLM servers (Ollama, LM Studio) when ALLOW_LOCAL_LLM is True.
    """
    try:
        validate_url_scheme(base_url)
    except FetchError as e:
        raise LLMProxyError(e.message, "INVALID_URL")

    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    if not parsed.hostname:
        raise LLMProxyError("Invalid base URL — no hostname found.", "INVALID_URL")

    # Check for local LLM bypass before SSRF validation
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if _is_local_endpoint(parsed.hostname, port):
        return  # Allowed local endpoint — skip SSRF check

    try:
        await resolve_and_validate(parsed.hostname)
    except FetchError as e:
        raise LLMProxyError(
            f"Target blocked: {e.message}",
            "BLOCKED_TARGET",
        )


async def send_to_llm(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout: int = LLM_TIMEOUT,
) -> LLMResponse:
    """
    Send a prompt to an OpenAI-compatible LLM endpoint.

    Args:
        api_key: Bearer token for authentication (NOT stored anywhere)
        base_url: The API base URL (e.g., "https://api.openai.com/v1")
        model: Model identifier (e.g., "gpt-4o-mini")
        system_prompt: System message to set model behavior
        user_prompt: User message (the attack payload or test)
        temperature: Sampling temperature (0.0 for deterministic)
        max_tokens: Maximum response length
        timeout: Request timeout in seconds

    Returns:
        LLMResponse with content, metadata, and timing

    Raises:
        LLMProxyError: On validation or request failure
    """
    # Step 1: Validate target URL against SSRF blocklist
    base_url = _normalize_base_url(base_url)
    await _validate_llm_target(base_url)

    # Step 2: Build request
    endpoint = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
    }
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Step 3: Send request with timing
    start_time = time.perf_counter()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        verify=True,
    ) as client:
        try:
            response = await client.post(endpoint, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise LLMProxyError(
                f"LLM request timed out after {timeout} seconds.",
                "TIMEOUT",
            )
        except httpx.ConnectError:
            raise LLMProxyError(
                "Could not connect to the LLM endpoint. Check the base URL.",
                "CONNECTION_FAILED",
            )
        except httpx.RequestError as e:
            raise LLMProxyError(
                f"Request failed: {str(e)}",
                "REQUEST_FAILED",
            )

    latency_ms = (time.perf_counter() - start_time) * 1000

    # Step 4: Handle errors
    if response.status_code == 401:
        raise LLMProxyError(
            "Authentication failed. Please check your API key.",
            "AUTH_FAILED",
        )
    elif response.status_code == 403:
        raise LLMProxyError(
            "Access denied. Your API key may not have permission for this model.",
            "ACCESS_DENIED",
        )
    elif response.status_code == 429:
        raise LLMProxyError(
            "Rate limit exceeded. Please wait a moment and try again.",
            "RATE_LIMITED",
        )
    elif response.status_code == 404:
        raise LLMProxyError(
            f"Model '{model}' not found. Check the model name and endpoint.",
            "MODEL_NOT_FOUND",
        )
    elif response.status_code >= 500:
        raise LLMProxyError(
            f"LLM service error (HTTP {response.status_code}). The provider may be experiencing issues.",
            "PROVIDER_ERROR",
        )
    elif response.status_code != 200:
        try:
            error_body = response.json()
            error_msg = error_body.get("error", {}).get("message", response.text[:200])
        except Exception:
            error_msg = response.text[:200]
        raise LLMProxyError(
            f"LLM request failed ({response.status_code}): {error_msg}",
            "REQUEST_FAILED",
        )

    # Step 5: Parse response
    try:
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason", "unknown")
        usage = data.get("usage", {})
        model_used = data.get("model", model)
    except (KeyError, IndexError, ValueError) as e:
        raise LLMProxyError(
            "Unexpected response format from the LLM endpoint.",
            "PARSE_ERROR",
        )

    return LLMResponse(
        content=content,
        model=model_used,
        finish_reason=finish_reason,
        usage=usage,
        latency_ms=round(latency_ms, 1),
    )


async def test_connection(
    api_key: str,
    base_url: str,
    model: str,
) -> LLMResponse:
    """
    Test the LLM connection with a simple, harmless prompt.

    Returns:
        LLMResponse from the test prompt

    Raises:
        LLMProxyError: If connection fails
    """
    return await send_to_llm(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt="You are a helpful assistant.",
        user_prompt="Reply with exactly: CONNECTION_OK",
        temperature=0.0,
        max_tokens=50,
        timeout=CONNECTION_TEST_TIMEOUT,
    )
