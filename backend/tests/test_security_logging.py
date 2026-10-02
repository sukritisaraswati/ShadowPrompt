"""Security tests for log redaction.

Blueprint 10.1 and the acceptance criteria require that an API key never
appears in a log line. The application avoids logging keys at all; this filter
is the backstop, and these tests are what stop the backstop from rotting.
"""

from __future__ import annotations

import logging

import pytest

from app.core.logging import REDACTED, SecretRedactingFilter, redact

pytestmark = pytest.mark.security

OPENAI_KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
ANTHROPIC_KEY = "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
GOOGLE_KEY = "AIzaSyA1b2C3d4E5f6G7h8I9j0KlMnOpQrStUvWx"


@pytest.mark.parametrize("key", [OPENAI_KEY, ANTHROPIC_KEY, GOOGLE_KEY])
def test_bare_keys_are_redacted(key: str) -> None:
    out = redact(f"calling provider with {key} now")
    assert key not in out
    assert REDACTED in out


def test_authorization_header_is_redacted() -> None:
    out = redact(f"Authorization: Bearer {OPENAI_KEY}")
    assert OPENAI_KEY not in out
    assert REDACTED in out


def test_x_api_key_header_is_redacted() -> None:
    out = redact(f"x-api-key: {ANTHROPIC_KEY}")
    assert ANTHROPIC_KEY not in out
    assert REDACTED in out


@pytest.mark.parametrize(
    "payload",
    [
        '{"api_key": "hunter2supersecretvalue"}',
        "api_key=hunter2supersecretvalue",
        '{"apiKey": "hunter2supersecretvalue"}',
        "API-KEY: hunter2supersecretvalue",
    ],
)
def test_key_bearing_structures_are_redacted(payload: str) -> None:
    out = redact(payload)
    assert "hunter2supersecretvalue" not in out
    assert REDACTED in out


def test_ordinary_text_is_left_alone() -> None:
    message = "Campaign 7 finished: 18 PASS, 2 FAIL, score 90"
    assert redact(message) == message


def test_filter_scrubs_the_log_message(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test.redaction.message")
    logger.addFilter(SecretRedactingFilter())

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info("connecting with %s", OPENAI_KEY)

    rendered = caplog.text
    assert OPENAI_KEY not in rendered
    assert REDACTED in rendered


def test_filter_scrubs_exception_text(caplog: pytest.LogCaptureFixture) -> None:
    """A key smuggled into an exception message must not reach the handler."""
    logger = logging.getLogger("test.redaction.exception")
    logger.addFilter(SecretRedactingFilter())

    with caplog.at_level(logging.ERROR, logger=logger.name):
        try:
            raise ValueError(f"auth rejected for {OPENAI_KEY}")
        except ValueError:
            logger.exception("LLM call failed")

    assert OPENAI_KEY not in caplog.text


def test_filter_scrubs_dict_args() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request %(api_key)s",
        # logging unwraps a single-element tuple holding a mapping.
        args=({"api_key": OPENAI_KEY},),
        exc_info=None,
    )
    SecretRedactingFilter().filter(record)
    assert OPENAI_KEY not in str(record.args)
