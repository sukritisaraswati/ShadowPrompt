"""Validation for uploaded HTML files.

The 2 MB ceiling is enforced earlier, at the HTTP layer, by
``app.core.limits.BodySizeLimitMiddleware``. These checks run on the bytes
that made it through: extension, declared type, and content sniffing so a
renamed PDF or executable is turned away.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath

from app.core.errors import AppError
from app.schemas.common import ErrorCode

ALLOWED_EXTENSIONS = frozenset({".html", ".htm"})
ALLOWED_CONTENT_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "text/plain", "application/octet-stream", ""}
)
_BINARY_SIGNATURES = (
    b"%PDF",
    b"\x89PNG",
    b"GIF8",
    b"\xff\xd8\xff",
    b"PK\x03\x04",
    b"\x1f\x8b",
    b"MZ",
    b"\x7fELF",
    b"Rar!",
    b"7z\xbc\xaf",
    b"\xca\xfe\xba\xbe",
)
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
_UNSAFE_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f<>:\"|?*]")


def sanitize_filename(filename: str | None) -> str:
    """A display-safe base name. Never used to build a filesystem path."""
    name = PureWindowsPath(PurePosixPath(filename or "").name).name
    name = _UNSAFE_NAME_CHARS.sub("_", name).strip(" .")
    return name[:255] or "upload.html"


def _unsupported(message: str, detail: str | None = None) -> AppError:
    return AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, message, status_code=415, detail=detail)


def validate_upload(filename: str, content_type: str | None, data: bytes, max_bytes: int) -> None:
    """Raise :class:`AppError` unless ``data`` is a plausible HTML document."""
    extension = PurePosixPath(filename.lower()).suffix
    if extension not in ALLOWED_EXTENSIONS:
        raise _unsupported("Only .html and .htm files can be scanned.", detail=extension or "none")

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_CONTENT_TYPES:
        raise _unsupported(
            "The file's declared type does not match an HTML document.", detail=declared[:100]
        )

    if len(data) > max_bytes:
        raise AppError(
            ErrorCode.UPLOAD_TOO_LARGE,
            f"Files larger than {max_bytes // (1024 * 1024)} MB cannot be scanned.",
            status_code=413,
        )
    if not data.strip():
        raise AppError(ErrorCode.VALIDATION_ERROR, "The uploaded file is empty.", status_code=400)

    head = data[:8192]
    if head.startswith(_BINARY_SIGNATURES):
        raise _unsupported("The file content is not HTML.", detail="binary signature")
    if b"\x00" in head and not head.startswith(_UTF16_BOMS):
        raise _unsupported("The file content is not HTML.", detail="binary content")
