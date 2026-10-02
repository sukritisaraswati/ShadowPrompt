"""A small HTTP client for the ShadowPrompt API, using only the standard library.

Keeping the CLI dependency-free means a CI job can install it in seconds and
nothing in it needs auditing beyond this package.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

USER_AGENT = "shadowprompt-cli/1.0"


class ApiError(Exception):
    """An error from the server, or a failure to reach it."""

    def __init__(self, code: str, message: str, *, status: int = 0, detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail

    def __str__(self) -> str:
        text = f"{self.message} [{self.code}]"
        return f"{text}: {self.detail}" if self.detail else text


@dataclass
class Upload:
    """A file for a multipart form field."""

    filename: str
    content: bytes
    content_type: str


def _multipart(field_name: str, upload: Upload) -> tuple[bytes, str]:
    boundary = f"shadowprompt-{uuid.uuid4().hex}"
    safe_name = upload.filename.replace('"', "").replace("\r", "").replace("\n", "")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{safe_name}"\r\n'
        f"Content-Type: {upload.content_type}\r\n\r\n"
    ).encode()
    body = head + upload.content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


@dataclass
class Client:
    server: str
    timeout: float = 120.0
    # Longest the client will wait in total for rate limits to clear.
    max_rate_limit_wait: float = 300.0
    sleep: Callable[[float], None] = time.sleep
    _waited: float = field(default=0.0, init=False)

    @property
    def base(self) -> str:
        return self.server.rstrip("/") + "/api/v1"

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        upload: tuple[str, Upload] | None = None,
        raw: bool = False,
    ) -> Any:
        """Send a request; returns parsed JSON, or bytes when ``raw``."""
        while True:
            try:
                return self._send(method, path, body=body, upload=upload, raw=raw)
            except ApiError as exc:
                if exc.status != 429:
                    raise
                wait = self._retry_after(exc)
                if self._waited + wait > self.max_rate_limit_wait:
                    raise
                self._waited += wait
                self.sleep(wait)

    @staticmethod
    def _retry_after(exc: ApiError) -> float:
        seconds = getattr(exc, "retry_after", None)
        return float(min(max(seconds or 5, 1), 60))

    def _send(
        self,
        method: str,
        path: str,
        *,
        body: Any,
        upload: tuple[str, Upload] | None,
        raw: bool,
    ) -> Any:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        data: bytes | None = None
        if upload is not None:
            data, headers["Content-Type"] = _multipart(*upload)
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(  # noqa: S310 - the server URL is the user's own
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                content = response.read()
        except urllib.error.HTTPError as exc:
            with exc:
                error = _from_http_error(exc)
            raise error from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ApiError(
                "SERVER_UNREACHABLE",
                f"Could not reach the ShadowPrompt server at {self.server}",
                detail=str(reason),
            ) from None
        if raw:
            return content
        return json.loads(content) if content else None


def _from_http_error(exc: urllib.error.HTTPError) -> ApiError:
    try:
        payload = json.loads(exc.read() or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    error = ApiError(
        str(payload.get("code") or f"HTTP_{exc.code}"),
        str(payload.get("message") or exc.reason or "Request failed"),
        status=exc.code,
        detail=payload.get("detail"),
    )
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after and retry_after.isdigit():
        error.retry_after = int(retry_after)  # type: ignore[attr-defined]
    return error
