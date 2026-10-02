"""Phase 5.3: testing a user's own chatbot through its endpoint."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing

import httpx
import pytest

from app.services.lab.chatbot import (
    SKIP_CANARY,
    SKIP_MEMORY,
    SKIP_USER_DATA,
    ChatbotSpec,
    ConversationMode,
    adapt_payload,
    canary_snippet,
    extract_reply,
    generate_canary,
    render_body,
    validate_template,
)
from app.services.lab.payloads import MatchMode, Objective, get_library
from tests.test_lab_api import wait_done

LIB = get_library()
BOT_URL = "https://bot.example.com/api/chat"
TOKEN = "Bearer bot-secret-TOKEN-0123456789abcdef"
CANARY = "PUFFIN-4821"
HISTORY_TEMPLATE = '{"message": "{{message}}", "history": "{{history}}", "client": "shadowprompt"}'
SERVER_TEMPLATE = '{"input": {"text": "{{message}}"}, "session": "{{conversation_id}}"}'
PLANTED = re.compile(r"\b[A-Z]{3,}-\d{4}\b")


def first(code: str, objective: Objective, live: bool | None = None):
    return next(
        p
        for p in LIB.for_level(code)
        if p.spec.objective is objective and (live is None or p.is_live == live)
    )


# --------------------------------------------------------------------------- #
# Templates and replies
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("template", "mode", "fragment"),
    [
        ('{"text": "hello"}', ConversationMode.MESSAGE, "{{message}}"),
        ("{message: {{message}}}", ConversationMode.MESSAGE, "valid JSON"),
        ('{"m": "{{message}}"}', ConversationMode.SERVER, "{{conversation_id}}"),
        ('{"m": "{{message}}"}', ConversationMode.HISTORY, "{{history}}"),
    ],
)
def test_unusable_templates_are_explained(template, mode, fragment) -> None:
    with pytest.raises(ValueError, match=re.escape(fragment)):
        validate_template(template, mode)


def test_history_mode_sends_turns_as_a_list_and_drops_the_system_prompt() -> None:
    spec = ChatbotSpec(HISTORY_TEMPLATE, "reply", ConversationMode.HISTORY)
    body = render_body(
        spec,
        [("system", "secret rules"), ("user", "hi"), ("assistant", "hello"), ("user", 'say "x"')],
        "c1",
    )
    assert body == {
        "message": 'say "x"',
        "history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        "client": "shadowprompt",
    }
    assert "secret rules" not in json.dumps(body)


def test_server_mode_sends_the_id_and_flattens_scripted_turns() -> None:
    spec = ChatbotSpec(SERVER_TEMPLATE, "", ConversationMode.SERVER)
    body = render_body(
        spec, [("user", "Say A."), ("assistant", "A."), ("user", "Now say B.")], "conv-9"
    )
    assert body["session"] == "conv-9"
    text = body["input"]["text"]
    assert text.startswith("Earlier in this conversation:")
    assert "Assistant: A." in text and text.endswith("Now say B.")


def test_placeholders_inside_longer_strings_are_filled() -> None:
    spec = ChatbotSpec('{"prompt": "User says: {{message}}"}', mode=ConversationMode.MESSAGE)
    assert render_body(spec, [("user", "hi")], "") == {"prompt": "User says: hi"}


@pytest.mark.parametrize(
    ("path", "body", "expected"),
    [
        ("reply", b'{"reply": "hello"}', "hello"),
        ("data.choices.0.text", b'{"data": {"choices": [{"text": "deep"}]}}', "deep"),
        ("", b"plain text answer", "plain text answer"),
        ("", b'"a json string"', "a json string"),
    ],
)
def test_reply_is_read_from_the_response_path(path, body, expected) -> None:
    assert extract_reply(ChatbotSpec("{}", path), body) == expected


@pytest.mark.parametrize(
    ("path", "body"),
    [("reply", b'{"answer": "x"}'), ("data.5", b'{"data": [1]}'), ("data", b'{"data": {"a": 1}}')],
)
def test_wrong_response_paths_are_errors(path, body) -> None:
    with pytest.raises(ValueError):
        extract_reply(ChatbotSpec("{}", path), body)


# --------------------------------------------------------------------------- #
# Adapting tests
# --------------------------------------------------------------------------- #


def test_canary_kit() -> None:
    canary = generate_canary()
    assert re.match(r"^[A-Z]{4,12}-\d{4}$", canary)
    assert canary in canary_snippet(canary)
    assert "access code" in canary_snippet(canary)


def test_secret_tests_need_the_canary() -> None:
    payload = first("D1", Objective.SECRET)
    assert adapt_payload(payload, None, ConversationMode.HISTORY).skipped == SKIP_CANARY
    adapted = adapt_payload(payload, CANARY, ConversationMode.HISTORY).payload
    protected = [s.text for s in adapted.spec.compliance_signals if s.match is MatchMode.NORMALIZED]
    assert protected == [CANARY, CANARY[::-1]]


def test_persona_tests_keep_their_marker_without_a_canary() -> None:
    payload = first("D2", Objective.PERSONA)
    adapted = adapt_payload(payload, None, ConversationMode.HISTORY).payload
    assert [s.match for s in adapted.spec.compliance_signals] == [MatchMode.PREFIX]


def test_indirect_tests_keep_the_planted_code_and_drop_library_private_data() -> None:
    payload = first("I1", Objective.INJECTION)
    adapted = adapt_payload(payload, None, ConversationMode.MESSAGE).payload
    assert [s.match for s in adapted.spec.compliance_signals] == [MatchMode.TOKEN]


def test_indirect_tests_that_only_steal_library_user_data_are_skipped_with_that_reason() -> None:
    payload = LIB.by_id("I2-009")
    assert {s.match for s in payload.spec.compliance_signals} == {MatchMode.NORMALIZED}
    assert adapt_payload(payload, CANARY, ConversationMode.HISTORY).skipped == SKIP_USER_DATA


def test_multi_turn_tests_need_a_bot_with_memory() -> None:
    live = first("D4", Objective.SECRET, live=True)
    assert adapt_payload(live, CANARY, ConversationMode.MESSAGE).skipped == SKIP_MEMORY
    assert adapt_payload(live, CANARY, ConversationMode.SERVER).payload is not None


# --------------------------------------------------------------------------- #
# The API, against a fake chatbot
# --------------------------------------------------------------------------- #


class FakeBot:
    """A chatbot with its own instructions, which contain the planted canary."""

    def __init__(self, vulnerable: bool, mode: str = "history") -> None:
        self.vulnerable = vulnerable
        self.mode = mode
        self.requests: list[tuple[httpx.Headers, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != TOKEN:
            echoed = request.headers.get("authorization")
            return httpx.Response(401, json={"error": f"bad token {echoed}"})
        body = json.loads(request.content)
        self.requests.append((request.headers, body))
        message = body["message"] if self.mode == "history" else body["input"]["text"]
        if message.startswith("Hello, please respond"):
            return httpx.Response(200, json={"reply": "OK"})
        if not self.vulnerable:
            return httpx.Response(200, json={"reply": "I'm sorry, but I can't help with that."})
        planted = " ".join(dict.fromkeys(PLANTED.findall(message)))
        reply = f"[DAN] Sure! The access code is {CANARY}. {planted} I have been PWNED."
        return httpx.Response(200, json={"reply": reply})


def connection(mode: str = "history", canary: str | None = CANARY, **chatbot) -> dict:
    template = HISTORY_TEMPLATE if mode == "history" else SERVER_TEMPLATE
    if mode == "message":
        template = '{"input": {"text": "{{message}}"}}'
    return {
        "provider": "chatbot",
        "base_url": BOT_URL,
        "model": "Acme helpdesk bot",
        "chatbot": {
            "body_template": template,
            "response_path": "reply",
            "mode": mode,
            "headers": {"Authorization": TOKEN},
            "canary": canary,
            **chatbot,
        },
    }


def start(client, conn: dict, levels: list[str], **extra) -> dict:
    session = client.post("/api/v1/lab/connect/test", json=conn)
    assert session.status_code == 200, session.text
    body = {"session_id": session.json()["session_id"], "connection": conn, "levels": levels}
    response = client.post("/api/v1/lab/campaigns", json={**body, **extra})
    assert response.status_code == 202, response.text
    return wait_done(client, response.json()["campaign_id"], timeout=60)


def test_connecting_sends_the_headers_and_reads_the_reply(client, use_model) -> None:
    bot = FakeBot(vulnerable=False)
    use_model(bot)
    body = client.post("/api/v1/lab/connect/test", json=connection()).json()
    assert body["reply_preview"] == "OK"
    assert body["provider"] == "chatbot"
    assert body["model_name"] == "Acme helpdesk bot"
    headers, sent = bot.requests[0]
    assert headers["authorization"] == TOKEN
    assert sent == {
        "message": "Hello, please respond with 'OK'.",
        "history": [],
        "client": "shadowprompt",
    }


def test_a_vulnerable_chatbot_fails_and_a_resistant_one_passes(client, use_model) -> None:
    use_model(FakeBot(vulnerable=True))
    bad = start(client, connection(), ["D1", "I1"], sample_size=3)
    assert {r["verdict"] for r in bad["results"]} == {"FAIL"}
    leak = next(r for r in bad["results"] if r["code"] == "D1" and r["objective"] == "secret")
    assert "access code disclosed" in leak["evaluation_detail"]["layer1"]["reasons"]
    assert bad["config"]["target"]["kind"] == "chatbot"
    assert bad["config"]["target"]["canary_planted"] is True

    use_model(FakeBot(vulnerable=False))
    good = start(client, connection(), ["D1", "I1"], sample_size=3)
    assert {r["verdict"] for r in good["results"]} == {"PASS"}
    assert all(r["evaluation_detail"]["target"] == "chatbot" for r in good["results"])


def test_without_a_canary_secret_tests_are_skipped_and_counted(client, use_model) -> None:
    use_model(FakeBot(vulnerable=False))
    result = start(client, connection(canary=None), ["D1"])
    skipped = result["config"]["target"]["skipped"]
    secret_tests = sum(1 for p in LIB.for_level("D1") if p.spec.objective is Objective.SECRET)
    assert skipped == {SKIP_CANARY: secret_tests}
    assert result["total_tests"] == 20 - secret_tests


def test_a_bot_that_keeps_history_gets_one_message_and_a_stable_id(client, use_model) -> None:
    bot = FakeBot(vulnerable=False, mode="server")
    use_model(bot)
    result = start(client, connection(mode="server"), ["D4"], sample_size=2)
    assert result["status"] == "completed"
    sessions: dict[str, list[str]] = {}
    for _, body in bot.requests[1:]:  # skip the connection probe
        sessions.setdefault(body["session"], []).append(body["input"]["text"])
    # One id per test, every turn of a test under the same id, one message each.
    assert len(sessions) == 2
    for turns in sessions.values():
        assert len(turns) >= 2
        assert not any(t.startswith("Earlier in this conversation") for t in turns)


def test_a_message_only_bot_skips_multi_turn_tests(client, use_model) -> None:
    use_model(FakeBot(vulnerable=False, mode="message"))
    result = start(client, connection(mode="message"), ["D3", "D4"], sample_size=3)
    assert result["config"]["target"]["skipped"] == {SKIP_MEMORY: 3}
    assert {r["code"] for r in result["results"]} == {"D3"}
    flattened = [r for r in result["results"] if r["evaluation_detail"].get("history_flattened")]
    assert all(isinstance(LIB.by_id(r["payload_id"]).spec.prompt, list) for r in flattened)


def test_nothing_runnable_is_an_error(client, use_model) -> None:
    use_model(FakeBot(vulnerable=False, mode="message"))
    session = client.post("/api/v1/lab/connect/test", json=connection(mode="message")).json()
    body = {
        "session_id": session["session_id"],
        "connection": connection(mode="message"),
        "levels": ["I5"],
    }
    response = client.post("/api/v1/lab/campaigns", json=body)
    assert response.status_code == 422
    assert SKIP_MEMORY in response.json()["detail"]


MESSAGE_ONLY = {"body_template": '{"m": "{{message}}"}', "mode": "message"}


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "openai_compatible"},
        {"chatbot": None},
        {"chatbot": {"body_template": '{"m": "{{message}}"}', "mode": "history"}},
        {"chatbot": {**MESSAGE_ONLY, "headers": {"Host": "x"}}},
        {"chatbot": {**MESSAGE_ONLY, "headers": {"X-A": "a\r\nInjected: 1"}}},
        {"chatbot": {**MESSAGE_ONLY, "canary": "not a canary"}},
    ],
)
def test_invalid_chatbot_settings_are_rejected(client, use_model, change) -> None:
    use_model(FakeBot(vulnerable=False))
    conn = {**connection(), **change}
    if change.get("provider") == "openai_compatible":
        conn["chatbot"] = connection()["chatbot"]
    assert client.post("/api/v1/lab/connect/test", json=conn).status_code == 422


@pytest.mark.security
def test_header_secrets_are_never_echoed_or_stored(client, use_model, db_session) -> None:
    bot = FakeBot(vulnerable=False)
    use_model(bot)
    secret = TOKEN.split()[1]
    bad = connection(headers={"Authorization": "Bearer wrong-" + secret})
    response = client.post("/api/v1/lab/connect/test", json=bad)
    assert response.status_code == 400
    assert secret not in response.text  # the bot echoed the token in its error

    result = start(client, connection(), ["D1"], sample_size=2)
    assert secret not in json.dumps(result)

    from app.core.config import get_settings

    db_path = get_settings().database_url.split("///", 1)[1]
    with closing(sqlite3.connect(db_path)) as conn:
        for (dump,) in conn.execute("select group_concat(config) from campaigns"):
            assert secret not in (dump or "")
        for (row,) in conn.execute("select group_concat(evaluation_detail) from test_results"):
            assert secret not in (row or "")


@pytest.mark.security
def test_chatbot_endpoints_go_through_the_network_guard(client, use_model) -> None:
    use_model(FakeBot(vulnerable=False))
    conn = connection()
    conn["base_url"] = "http://169.254.169.254/latest/api/chat"
    body = client.post("/api/v1/lab/connect/test", json=conn).json()
    assert body["code"] == "BLOCKED_TARGET"
