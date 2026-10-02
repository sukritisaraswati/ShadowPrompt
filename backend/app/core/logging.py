"""Logging setup with mandatory secret redaction.

Blueprint section 10.1 requires that API keys are *never* written to logs,
databases, error messages or analytics. Developers forget; a filter does not.
Every log record emitted by the application passes through
:class:`SecretRedactingFilter`, which rewrites anything that looks like a
credential before the record reaches a handler.

This is defence in depth, not the primary control. The primary control is that
the backend holds a user's key in request-scoped memory only and never passes
it to a logger in the first place.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

REDACTED = "[REDACTED]"

# Ordered most-specific first. Each pattern keeps any identifying prefix so a
# redacted log line still says *what kind* of secret was suppressed.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Anthropic keys: sk-ant-api03-...
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), f"sk-ant-{REDACTED}"),
    # OpenAI and compatible: sk-..., sk-proj-...
    (re.compile(r"sk-[A-Za-z0-9_\-]{12,}"), f"sk-{REDACTED}"),
    # Google / Gemini: AIza...
    (re.compile(r"AIza[A-Za-z0-9_\-]{10,}"), f"AIza{REDACTED}"),
    # HTTP auth headers of any scheme.
    (
        re.compile(r"(?i)\b(authorization\s*[:=]\s*)(bearer\s+)?\S+"),
        lambda m: f"{m.group(1)}{m.group(2) or ''}{REDACTED}",
    ),
    (re.compile(r"(?i)\b(x-api-key\s*[:=]\s*)\S+"), lambda m: f"{m.group(1)}{REDACTED}"),
    # JSON or kwargs style: api_key="...", "apiKey": '...'
    (
        re.compile(r"""(?i)(["']?api[_-]?key["']?\s*[:=]\s*)(["']?)([^"'\s,}\]]+)(\2)"""),
        lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(4)}",
    ),
)


def redact(text: str) -> str:
    """Return ``text`` with any credential-shaped substring replaced."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SecretRedactingFilter(logging.Filter):
    """Scrub credential-shaped values from a log record before it is emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = self._redact_args(record.args)
        # Never let an exception message smuggle a key out via the traceback.
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            if exc.args and isinstance(exc.args[0], str):
                exc.args = (redact(exc.args[0]), *exc.args[1:])
        return True

    @staticmethod
    def _redact_args(args: Any) -> Any:
        if isinstance(args, dict):
            return {k: redact(v) if isinstance(v, str) else v for k, v in args.items()}
        if isinstance(args, tuple):
            return tuple(redact(a) if isinstance(a, str) else a for a in args)
        return args


def configure_logging(level: str = "INFO") -> None:
    """Install the root logging configuration with redaction attached."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(SecretRedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn installs its own handlers; route them through ours so access and
    # error logs are redacted too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
