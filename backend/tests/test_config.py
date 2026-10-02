"""Settings parse the way deployments actually provide them: as strings."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:8080", ["http://localhost:8080"]),
        ("http://a.example, http://b.example", ["http://a.example", "http://b.example"]),
        ('["http://a.example", "http://b.example"]', ["http://a.example", "http://b.example"]),
    ],
)
def test_cors_origins_accept_plain_comma_and_json_forms(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: list[str]
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", value)
    assert Settings().cors_origins == expected


def _env_example() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _compose_backend_env() -> dict[str, str]:
    """The backend's environment block in docker-compose.yml, with defaults applied."""
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    block = text.split("\n  backend:\n", 1)[1].split("\n    environment:\n", 1)[1]
    values = {}
    for line in block.splitlines():
        if not line.startswith("      ") or line.strip().startswith("#"):
            if line.strip() and not line.startswith("      "):
                break
            continue
        key, _, value = line.strip().partition(":")
        value = value.strip().strip('"')
        # ${NAME:-default} -> default; ${NAME} -> a placeholder.
        value = re.sub(r"\$\{[A-Z0-9_]+:-([^}]*)\}", r"\1", value)
        value = re.sub(r"\$\{[A-Z0-9_]+(?::\?[^}]*)?\}", "placeholder", value)
        values[key] = value
    return values


@pytest.mark.parametrize("source", ["env_example", "compose"])
def test_shipped_configuration_starts_the_backend(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    """Every value the project ships must parse, or the deployment will not start."""
    values = _env_example() if source == "env_example" else _compose_backend_env()
    assert values, source
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings = Settings()
    assert settings.cors_origins
