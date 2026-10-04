"""``shadowprompt campaign --chatbot``: testing your own chatbot from CI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shadowprompt_cli import main as cli
from shadowprompt_cli.chatbot import ChatbotFileError, load_chatbot
from tests.test_cli import FakeServer, server  # noqa: F401 - the server fixture

BOT_TOKEN = "Bearer ci-secret-TOKEN-0123456789"  # noqa: S105 - a test value


def bot_file(tmp_path: Path, **overrides) -> Path:
    data = {
        "name": "Helpdesk bot",
        "url": "https://bot.example.com/api/chat",
        "mode": "server",
        "body_template": {"message": "{{message}}", "conversation_id": "{{conversation_id}}"},
        "response_path": "reply",
        "headers": {"Authorization": "${BOT_TOKEN}"},
        "canary": "PUFFIN-4821",
        "indirect_delivery": "hosted",
        **overrides,
    }
    path = tmp_path / "bot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_a_chatbot_file_reads_secrets_from_the_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    target = load_chatbot(str(bot_file(tmp_path)))
    assert target.chatbot["headers"] == {"Authorization": BOT_TOKEN}
    assert json.loads(target.chatbot["body_template"])["conversation_id"] == "{{conversation_id}}"
    assert target.indirect_delivery == "hosted"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({}, "BOT_TOKEN is not set"),
        ({"url": ""}, "needs 'url'"),
        ({"mode": "telepathy"}, "mode must be"),
        ({"indirect_delivery": "carrier pigeon"}, "indirect_delivery must be"),
        ({"headers": ["Authorization"]}, "headers must be"),
    ],
)
def test_broken_chatbot_files_are_explained(tmp_path, monkeypatch, overrides, fragment) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ChatbotFileError, match=fragment):
        load_chatbot(str(bot_file(tmp_path, **overrides)))


def test_unreadable_files_are_explained(tmp_path) -> None:
    with pytest.raises(ChatbotFileError, match="cannot read"):
        load_chatbot(str(tmp_path / "missing.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ChatbotFileError, match="not valid JSON"):
        load_chatbot(str(bad))


def routes(fake: FakeServer) -> None:
    fake.route("POST", "/lab/connect/test", {"session_id": "sess-bot"})
    fake.route(
        "POST", "/lab/campaigns", lambda r: (202, {}, {"campaign_id": "camp-bot", "total_tests": 3})
    )
    fake.route(
        "GET",
        "/lab/campaigns/camp-bot",
        {
            "status": "completed",
            "total_tests": 3,
            "completed_tests": 3,
            "overall_score": 66.7,
            "rating": {"label": "Vulnerable"},
            "track_scores": [{"track": "direct", "name": "Direct prompt injection", "score": 66.7}],
            "level_scores": [{"code": "D2", "level": 2, "name": "Persona", "score": 66.7}],
            "top_fixes": [{"title": "Persona and role switching", "failed_tests": 1}],
            "config": {"target": {"skipped": {"needs the canary planted": 2}}},
            "results": [
                {"payload_id": "D2-001", "level": 2, "name": "DAN", "verdict": "FAIL"},
            ],
            "error_message": None,
        },
    )


def test_campaign_against_a_chatbot(server, tmp_path, monkeypatch, capsys) -> None:  # noqa: F811
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    routes(server)
    args = [
        "--server",
        server.url,
        "campaign",
        "--chatbot",
        str(bot_file(tmp_path)),
        "--levels",
        "D2",
        "--min-score",
        "50",
    ]
    assert cli.main(args) == cli.EXIT_OK

    started = next(r for r in server.requests if r.path == "/api/v1/lab/campaigns").json()
    connection = started["connection"]
    assert connection["provider"] == "chatbot"
    assert connection["base_url"] == "https://bot.example.com/api/chat"
    assert connection["api_key"] is None
    assert connection["chatbot"]["headers"] == {"Authorization": BOT_TOKEN}
    assert connection["chatbot"]["mode"] == "server"
    assert started["indirect_delivery"] == "hosted"

    out = capsys.readouterr()
    assert "Helpdesk bot: 66.7/100 (Vulnerable)" in out.out
    assert "Direct prompt injection: 66.7" in out.out
    assert "1. Persona and role switching (1 failed)" in out.out
    assert "Skipped 2: needs the canary planted" in out.out
    assert BOT_TOKEN not in out.out + out.err


def test_a_target_is_required(server, capsys) -> None:  # noqa: F811
    assert cli.main(["--server", server.url, "campaign", "--levels", "D1"]) == cli.EXIT_ERROR
    assert "--chatbot FILE" in capsys.readouterr().err


def test_an_unset_secret_stops_the_run_before_anything_is_sent(
    server,  # noqa: F811
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    routes(server)
    args = ["--server", server.url, "campaign", "--chatbot", str(bot_file(tmp_path))]
    assert cli.main(args) == cli.EXIT_ERROR
    assert server.requests == []
    assert "BOT_TOKEN is not set" in capsys.readouterr().err
