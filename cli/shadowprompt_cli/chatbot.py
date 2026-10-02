"""Chatbot target files for ``shadowprompt campaign --chatbot bot.json``.

A chatbot file describes the user's own chatbot endpoint::

    {
      "name": "Acme helpdesk bot",
      "url": "https://bot.example.com/api/chat",
      "mode": "history",
      "body_template": {"message": "{{message}}", "history": "{{history}}"},
      "response_path": "reply",
      "headers": {"Authorization": "Bearer ${BOT_TOKEN}"},
      "canary": "PUFFIN-4821",
      "indirect_delivery": "inline"
    }

Header values may use ``${NAME}`` to read an environment variable, so tokens
stay in CI secrets instead of files. A variable that is not set is an
error, never an empty header.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
MODES = ("history", "server", "message")
DELIVERIES = ("inline", "hosted")


class ChatbotFileError(ValueError):
    """The chatbot file is missing, malformed, or refers to an unset variable."""


@dataclass(frozen=True)
class ChatbotTarget:
    name: str
    url: str
    chatbot: dict
    indirect_delivery: str


def _expand(value: str, where: str) -> str:
    def lookup(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in os.environ:
            raise ChatbotFileError(f"{where} uses ${{{name}}}, but {name} is not set")
        return os.environ[name]

    return _ENV.sub(lookup, value)


def load_chatbot(path: str) -> ChatbotTarget:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ChatbotFileError(f"cannot read {path}: {exc.strerror or exc}") from None
    except json.JSONDecodeError as exc:
        raise ChatbotFileError(f"{path} is not valid JSON: {exc.msg}") from None
    if not isinstance(data, dict):
        raise ChatbotFileError(f"{path} must contain a JSON object")
    for field in ("url", "body_template"):
        if not data.get(field):
            raise ChatbotFileError(f"{path} needs {field!r}")
    mode = data.get("mode", "history")
    if mode not in MODES:
        raise ChatbotFileError(f"mode must be one of {', '.join(MODES)}")
    delivery = data.get("indirect_delivery", "inline")
    if delivery not in DELIVERIES:
        raise ChatbotFileError(f"indirect_delivery must be one of {', '.join(DELIVERIES)}")
    template = data["body_template"]
    if not isinstance(template, str):
        template = json.dumps(template)
    headers = data.get("headers") or {}
    if not isinstance(headers, dict):
        raise ChatbotFileError("headers must be an object of name: value")
    return ChatbotTarget(
        name=str(data.get("name") or "My chatbot"),
        url=str(data["url"]),
        chatbot={
            "body_template": template,
            "response_path": str(data.get("response_path", "")),
            "mode": mode,
            "headers": {
                str(name): _expand(str(value), f"header {name}") for name, value in headers.items()
            },
            "canary": data.get("canary"),
        },
        indirect_delivery=delivery,
    )
