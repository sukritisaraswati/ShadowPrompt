"""The API surface contract.

Phase 0 fixes the route list from blueprint section 9 so later releases fill in
behaviour without renegotiating paths with the frontend. If an endpoint
disappears or moves, these tests fail.
"""

from __future__ import annotations

import pytest

LAB_ENDPOINTS = [
    ("POST", "/api/v1/lab/connect/test"),
    ("POST", "/api/v1/lab/campaigns"),
    ("GET", "/api/v1/lab/campaigns"),
    ("GET", "/api/v1/lab/campaigns/{campaign_id}"),
    ("GET", "/api/v1/lab/campaigns/{campaign_id}/stream"),
    ("DELETE", "/api/v1/lab/campaigns/{campaign_id}"),
    ("POST", "/api/v1/lab/campaigns/{campaign_id}/stop"),
    ("POST", "/api/v1/lab/campaigns/{campaign_id}/pause"),
    ("POST", "/api/v1/lab/campaigns/{campaign_id}/resume"),
    ("POST", "/api/v1/lab/reports"),
    ("GET", "/api/v1/lab/payload-library/summary"),
    ("GET", "/api/v1/lab/capabilities"),
    ("POST", "/api/v1/lab/payload-packs"),
    ("GET", "/api/v1/lab/payload-packs"),
    ("GET", "/api/v1/lab/payload-packs/schema"),
    ("GET", "/api/v1/lab/payload-packs/example"),
    ("GET", "/api/v1/lab/payload-packs/{pack_id}"),
    ("DELETE", "/api/v1/lab/payload-packs/{pack_id}"),
]

SCAN_ENDPOINTS = [
    ("POST", "/api/v1/scan/url"),
    ("POST", "/api/v1/scan/html"),
    ("GET", "/api/v1/scan/results"),
    ("GET", "/api/v1/scan/results/{scan_id}"),
    ("GET", "/api/v1/scan/demo-pages"),
    ("POST", "/api/v1/scan/demo-pages/{demo_id}/scan"),
    ("POST", "/api/v1/scan/reports"),
]

ALL_ENDPOINTS = LAB_ENDPOINTS + SCAN_ENDPOINTS


@pytest.mark.parametrize(("method", "path"), ALL_ENDPOINTS)
def test_endpoint_is_documented(client, method: str, path: str) -> None:
    """Every blueprint endpoint appears in the OpenAPI schema."""
    spec = client.get("/openapi.json").json()
    assert path in spec["paths"], f"{path} missing from OpenAPI schema"
    assert method.lower() in spec["paths"][path], f"{method} {path} missing"


@pytest.mark.parametrize(("method", "path"), ALL_ENDPOINTS)
def test_no_endpoint_is_still_a_stub(client, method: str, path: str) -> None:
    """Release 3 implements the whole blueprint API: nothing returns 501 any more."""
    concrete = path.format(
        campaign_id="00000000-0000-4000-8000-000000000000",
        scan_id="00000000-0000-4000-8000-000000000000",
        demo_id="no-such-demo",
        pack_id="00000000-0000-4000-8000-000000000000",
    )
    assert client.request(method, concrete).status_code != 501


def test_lab_and_scan_are_separate_route_groups(client) -> None:
    """The two services share a backend but keep distinct prefixes."""
    paths = client.get("/openapi.json").json()["paths"]
    lab = {p for p in paths if p.startswith("/api/v1/lab/")}
    scan = {p for p in paths if p.startswith("/api/v1/scan/")}

    assert lab and scan
    assert not lab & scan


def test_unknown_route_returns_error_envelope(client) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
