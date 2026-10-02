"""CLI behaviour against a fake ShadowPrompt server."""

from __future__ import annotations

import functools
import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from shadowprompt_cli import main as cli
from shadowprompt_cli.client import ApiError, Client

Handler = Callable[["Request"], tuple[int, dict, object]]


class Request:
    def __init__(self, method: str, path: str, headers: dict, body: bytes) -> None:
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body

    def json(self) -> dict:
        return json.loads(self.body)


class FakeServer:
    """Routes (method, path) to handlers and records every request."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Handler] = {}
        self.requests: list[Request] = []
        server = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return None

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                request = Request(
                    self.command, self.path, dict(self.headers), self.rfile.read(length)
                )
                server.requests.append(request)
                handler = server.routes.get((self.command, self.path))
                if handler is None:
                    status, headers, body = 404, {}, {"code": "NOT_FOUND", "message": "Not found"}
                else:
                    status, headers, body = handler(request)
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_DELETE = _handle  # noqa: N815

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )

    def route(self, method: str, path: str, handler: Handler | dict) -> None:
        if isinstance(handler, dict):
            payload = handler
            self.routes[(method, "/api/v1" + path)] = lambda _r: (200, {}, payload)
        else:
            self.routes[(method, "/api/v1" + path)] = handler


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    fake.thread.start()
    yield fake
    fake.httpd.shutdown()
    fake.httpd.server_close()


def scan_result(score: int, severity: str, findings: int = 0) -> dict:
    return {
        "id": f"scan-{score:04d}-0000",
        "score": score,
        "severity": {"level": severity},
        "findings": [
            {
                "category_label": "Instruction override",
                "source_label": "HTML comment",
                "matched_rule": "instruction_override.ignore_previous",
                "obfuscation_label": "Base64" if i == 0 else None,
                "evidence_text": "ignore all previous instructions",
            }
            for i in range(findings)
        ],
    }


def write_pages(tmp_path: Path, names: list[str]) -> Path:
    site = tmp_path / "site"
    (site / "blog").mkdir(parents=True)
    for name in names:
        (site / name).write_text(f"<html><body><p>{name}</p></body></html>", encoding="utf-8")
    (site / "style.css").write_text("body{}", encoding="utf-8")
    return site


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #


def test_scan_passes_when_every_page_is_below_the_threshold(server, tmp_path, capsys) -> None:
    site = write_pages(tmp_path, ["index.html", "blog/post.htm"])
    server.route("POST", "/scan/html", lambda r: (201, {}, scan_result(0, "clean")))

    code = cli.main(["--server", server.url, "scan", str(site)])

    assert code == cli.EXIT_OK
    uploads = [r for r in server.requests if r.path == "/api/v1/scan/html"]
    assert len(uploads) == 2  # the stylesheet is skipped
    assert (
        b'filename="index.html"' in uploads[1].body or b'filename="index.html"' in uploads[0].body
    )
    assert b"<p>index.html</p>" in b"".join(u.body for u in uploads)
    assert "2 scanned, 0 at or above 'high': passed." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("severity", "fail_on", "expected"),
    [
        ("medium", "high", cli.EXIT_OK),
        ("high", "high", cli.EXIT_THRESHOLD),
        ("critical", "high", cli.EXIT_THRESHOLD),
        ("low", "low", cli.EXIT_THRESHOLD),
        ("critical", "never", cli.EXIT_OK),
    ],
)
def test_scan_threshold(server, tmp_path, severity, fail_on, expected) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>x</p>", encoding="utf-8")
    server.route("POST", "/scan/html", lambda r: (201, {}, scan_result(70, severity, 1)))
    assert cli.main(["--server", server.url, "scan", str(page), "--fail-on", fail_on]) == expected


def test_scan_urls_use_the_server_side_fetcher(server, capsys) -> None:
    server.route("POST", "/scan/url", lambda r: (201, {}, scan_result(88, "critical", 2)))
    code = cli.main(["--server", server.url, "--json", "scan", "https://example.com/a"])
    assert code == cli.EXIT_THRESHOLD
    assert server.requests[0].json() == {"url": "https://example.com/a", "render": False}
    out = json.loads(capsys.readouterr().out)
    assert out["results"][0]["severity"] == "critical"
    assert out["results"][0]["findings"][0]["decoded_from"] == "Base64"


def test_render_is_requested_for_files_and_urls(server, tmp_path) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>x</p>", encoding="utf-8")
    server.route("POST", "/scan/html", lambda r: (201, {}, scan_result(0, "clean")))
    server.route("POST", "/scan/url", lambda r: (201, {}, scan_result(0, "clean")))

    args = ["--server", server.url, "scan", "--render", str(page), "https://example.com/"]
    assert cli.main(args) == cli.EXIT_OK

    upload = next(r for r in server.requests if r.path.endswith("/scan/html"))
    assert b'name="render"' in upload.body
    assert b"\r\n\r\ntrue\r\n" in upload.body
    url = next(r for r in server.requests if r.path.endswith("/scan/url"))
    assert url.json()["render"] is True


def test_a_page_that_cannot_be_scanned_fails_the_build(server, tmp_path, capsys) -> None:
    server.route(
        "POST",
        "/scan/url",
        lambda r: (400, {}, {"code": "BLOCKED_TARGET", "message": "Private address"}),
    )
    code = cli.main(
        ["--server", server.url, "scan", "https://10.0.0.1/", str(tmp_path / "gone.html")]
    )
    assert code == cli.EXIT_THRESHOLD
    out = capsys.readouterr().out
    assert "BLOCKED_TARGET" in out
    assert "file not found" in out


def test_scan_writes_reports_and_github_outputs(server, tmp_path, monkeypatch) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>x</p>", encoding="utf-8")
    output, summary = tmp_path / "out.txt", tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    server.route("POST", "/scan/html", lambda r: (201, {}, scan_result(45, "medium", 1)))
    server.route("POST", "/scan/reports", lambda r: (200, {}, b"<html>report</html>"))

    reports = tmp_path / "reports"
    code = cli.main(["--server", server.url, "scan", str(page), "--report-dir", str(reports)])

    assert code == cli.EXIT_OK
    assert [p.read_bytes() for p in reports.iterdir()] == [b"<html>report</html>"]
    assert "max-score=45" in output.read_text()
    assert "failed=false" in output.read_text()
    assert "| medium | 45 | 1 |" in summary.read_text()


def test_unreachable_server_is_an_error(tmp_path, capsys) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>x</p>", encoding="utf-8")
    code = cli.main(["--server", "http://127.0.0.1:9", "scan", str(page)])
    assert code == cli.EXIT_ERROR
    assert "Could not reach the ShadowPrompt server" in capsys.readouterr().err


def test_rate_limits_are_waited_out(server) -> None:
    calls = {"n": 0}

    def limited(_r):
        calls["n"] += 1
        if calls["n"] < 3:
            return 429, {"Retry-After": "7"}, {"code": "RATE_LIMITED", "message": "Too many"}
        return 201, {}, scan_result(0, "clean")

    server.route("POST", "/scan/url", limited)
    slept: list[float] = []
    client = Client(server.url, sleep=slept.append)
    result = client.request("POST", "/scan/url", body={"url": "https://example.com"})
    assert result["severity"]["level"] == "clean"
    assert slept == [7.0, 7.0]


def test_rate_limit_waiting_is_bounded(server) -> None:
    server.route(
        "POST",
        "/scan/url",
        lambda r: (429, {"Retry-After": "60"}, {"code": "RATE_LIMITED", "message": "Too many"}),
    )
    client = Client(server.url, sleep=lambda _s: None, max_rate_limit_wait=100)
    with pytest.raises(ApiError) as info:
        client.request("POST", "/scan/url", body={"url": "https://example.com"})
    assert info.value.status == 429


# --------------------------------------------------------------------------- #
# campaign
# --------------------------------------------------------------------------- #

KEY = "sk-test-NEVER-ON-THE-COMMAND-LINE-0123456789"


def campaign_routes(server: FakeServer, *, score: float | None, status: str = "completed"):
    polls = {"n": 0}
    server.route("POST", "/lab/connect/test", {"session_id": "sess-1"})
    server.route("POST", "/lab/payload-packs", lambda r: (201, {}, {"id": "pack-1"}))
    server.route(
        "POST", "/lab/campaigns", lambda r: (202, {}, {"campaign_id": "camp-1", "total_tests": 2})
    )

    def poll(_r):
        polls["n"] += 1
        done = polls["n"] >= 2
        return (
            200,
            {},
            {
                "status": status if done else "running",
                "total_tests": 2,
                "completed_tests": 2 if done else 1,
                "overall_score": score if done else None,
                "rating": {"label": "Moderate"} if done and score is not None else None,
                "level_scores": [{"level": 1, "name": "Basic Jailbreak", "score": score}],
                "results": [
                    {"payload_id": "L1-001", "level": 1, "name": "Ignore", "verdict": "PASS"},
                    {"payload_id": "L1-002", "level": 1, "name": "Override", "verdict": "FAIL"},
                ],
                "error_message": "Model unreachable" if status == "failed" else None,
            },
        )

    server.route("GET", "/lab/campaigns/camp-1", poll)
    server.route("POST", "/lab/reports", lambda r: (200, {}, b"%PDF-1.7 report"))


def campaign_args(server: FakeServer, *extra: str) -> list[str]:
    return [
        "--server",
        server.url,
        "campaign",
        "--base-url",
        "https://api.example.com/v1",
        "--model",
        "gpt-test",
        "--levels",
        "1",
        *extra,
    ]


@pytest.fixture(autouse=True)
def _no_polling_delay(monkeypatch) -> None:
    monkeypatch.setattr(cli, "Client", functools.partial(Client, sleep=lambda _s: None))


def test_campaign_passes_above_the_minimum(server, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("SHADOWPROMPT_LLM_API_KEY", KEY)
    campaign_routes(server, score=75.0)
    pack = tmp_path / "pack.json"
    pack.write_text('{"format": "shadowprompt-pack/1"}', encoding="utf-8")
    report = tmp_path / "out" / "report.pdf"

    code = cli.main(
        campaign_args(
            server,
            "--min-score",
            "70",
            "--languages",
            "es,hi",
            "--pack",
            str(pack),
            "--report",
            str(report),
        )
    )

    assert code == cli.EXIT_OK
    started = next(r for r in server.requests if r.path == "/api/v1/lab/campaigns")
    body = started.json()
    assert body["connection"]["api_key"] == KEY
    assert body["languages"] == ["es", "hi"]
    assert body["custom_pack_ids"] == ["pack-1"]
    assert body["levels"] == [1]
    assert report.read_bytes() == b"%PDF-1.7 report"
    assert (
        next(r for r in server.requests if r.path == "/api/v1/lab/reports").json()["format"]
        == "pdf"
    )
    captured = capsys.readouterr()
    assert "gpt-test: 75/100 (Moderate)" in captured.out
    assert "FAIL     L1-002" in captured.out
    assert KEY not in captured.out + captured.err


def test_campaign_below_the_minimum_fails_the_build(server, monkeypatch) -> None:
    campaign_routes(server, score=55.0)
    assert cli.main(campaign_args(server, "--min-score", "70")) == cli.EXIT_THRESHOLD


def test_a_campaign_with_no_score_fails(server) -> None:
    campaign_routes(server, score=None)
    assert cli.main(campaign_args(server)) == cli.EXIT_THRESHOLD


def test_a_failed_campaign_is_an_error(server, capsys) -> None:
    campaign_routes(server, score=None, status="failed")
    assert cli.main(campaign_args(server)) == cli.EXIT_ERROR
    assert "Model unreachable" in capsys.readouterr().out


def test_connection_errors_are_reported(server, capsys) -> None:
    server.route(
        "POST",
        "/lab/connect/test",
        lambda r: (400, {}, {"code": "LLM_AUTH_FAILED", "message": "The API key was rejected."}),
    )
    assert cli.main(campaign_args(server)) == cli.EXIT_ERROR
    assert "LLM_AUTH_FAILED" in capsys.readouterr().err


def test_the_key_is_not_accepted_as_an_argument(server) -> None:
    with pytest.raises(SystemExit):
        cli.main(campaign_args(server, "--api-key", KEY))


def test_campaign_writes_github_outputs(server, tmp_path, monkeypatch) -> None:
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    campaign_routes(server, score=91.5)
    assert cli.main(campaign_args(server, "--json")) == cli.EXIT_OK
    text = output.read_text()
    assert "score=91.5" in text and "campaign-id=camp-1" in text and "failed=false" in text


@pytest.mark.parametrize("levels", ["0", "6", "a,b", ""])
def test_invalid_levels_are_rejected(server, levels) -> None:
    with pytest.raises(SystemExit):
        cli.main([*campaign_args(server)[:-2], "--levels", levels])
