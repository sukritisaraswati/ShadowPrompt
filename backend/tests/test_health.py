"""Tests for the platform health endpoint."""

from __future__ import annotations


def test_health_reports_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["environment"] == "test"
    assert body["version"]
    assert body["uptime_seconds"] >= 0


def test_health_sets_security_headers(client) -> None:
    """Baseline hardening headers are applied to every response."""
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in headers["content-security-policy"]
