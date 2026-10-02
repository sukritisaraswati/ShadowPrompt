"""Application error type.

Services raise :class:`AppError` with a stable code. A single handler in
``app.main`` turns it into the shared error envelope, so no route has to
hand-build error responses and no internal detail leaks by accident.
"""

from __future__ import annotations

from app.schemas.common import ErrorCode


class AppError(Exception):
    """A failure the client can act on, with a stable machine-readable code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 400,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}
