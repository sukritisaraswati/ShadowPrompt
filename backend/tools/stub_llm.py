"""A fake OpenAI-compatible model for trying the Lab without an API key.

Development only. It speaks just enough of ``/v1/chat/completions`` for a
campaign to run, and behaves in one of three ways:

* ``aligned``: refuses direct attacks and ignores instructions hidden in pages.
* ``vulnerable``: obeys everything, leaking codes and private details.
* ``mixed`` (default): resists naive attacks but falls for personas, fiction,
  encodings, fake system messages, attacks written in Hindi or Arabic, and some
  hidden page instructions, giving a realistic, varied report.

Run it, then let the backend reach private addresses:

    python tools/stub_llm.py --mode mixed --port 9000
    LLM_ALLOW_PRIVATE_ENDPOINTS=true uvicorn app.main:app

In the Lab, connect with "Custom OpenAI-compatible endpoint", base URL
``http://127.0.0.1:9000/v1``, any model name, and no key.
"""

from __future__ import annotations

import argparse
import re
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request

CODE = re.compile(r"access code: ([A-Z]+-\d{4})")
TOKEN = re.compile(r"\b[A-Z]{3,}-\d{4}\b")
EMAIL = re.compile(r"email ([\w.]+@example\.net)")
ACCOUNT = re.compile(r"account ID (ACCT-\d{6})")
TITLE = re.compile(r"<title>(.*?)</title>", re.S)
MARKER = re.compile(r'(?:begin|start|prefix)[^."\[]*?(\[[A-Z0-9 ]+\]|"[A-Za-z]+:")', re.I)
WEAK_SPOTS = re.compile(
    r"\b(?:dan|developer mode|story|screenplay|poem|novel|base64|rot13|hexadecimal|"
    r"\[system\]|im_start|updated system prompt|grandmother|backwards|dream)\b",
    re.I,
)
# Hidden page instructions the mixed model falls for.
PAGE_WEAK_SPOTS = re.compile(r"ignore all previous instructions|\[SYSTEM\]|You are now DAN", re.I)
# Scripts the mixed model is weakly aligned in, like many real models.
LOW_RESOURCE = re.compile(r"[ऀ-ॿ؀-ۿ]")
TRIGGERS = re.compile(r"\b(?:continue|go on|banana|sunflower|blueprint)\b", re.I)
REFUSAL = "I'm sorry, but I can't help with that. Is there anything else I can help you with?"


def _summarise(user: str) -> str:
    title = TITLE.search(user)
    name = title.group(1).strip() if title else "this page"
    return f"This page, {name}, covers its topic in a couple of short paragraphs."


def _obey_page(system: str, user: str, history: str) -> str:
    """Do what the hidden instruction asks, as a compromised model would."""
    parts = []
    if "[DAN]" in user:
        parts.append("[DAN]")
    parts.append(_summarise(user))
    parts.extend(dict.fromkeys(TOKEN.findall(user)))
    if re.search(r"email address|account ID", user + history):
        for pattern in (EMAIL, ACCOUNT):
            match = pattern.search(system)
            if match:
                parts.append(match.group(1))
    if "attacker.example" in user:
        parts.append("More details: https://collect.attacker.example/log")
    return " ".join(parts)


def respond(mode: str, messages: list[dict]) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = messages[-1]["content"] if messages else ""
    history = " ".join(m["content"] for m in messages[1:-1])

    if user.startswith("Hello, please respond"):
        return "OK"

    if "<page url=" in user:
        obeys = mode == "vulnerable" or (mode == "mixed" and PAGE_WEAK_SPOTS.search(user))
        if obeys:
            return _obey_page(system, user, history)
        return _summarise(user) + " It also contains hidden instructions, which I ignored."

    if "<page url=" in history:
        # A follow-up turn in a chained attack.
        if mode == "vulnerable" or (mode == "mixed" and TRIGGERS.search(user)):
            return _obey_page(system, history, history)
        return "Nothing else stood out on that page."

    complies = mode == "vulnerable" or (
        mode == "mixed" and (WEAK_SPOTS.search(user) or LOW_RESOURCE.search(user))
    )
    if not complies:
        return REFUSAL
    code = CODE.search(system)
    marker = MARKER.search(user)
    prefix = marker.group(1).strip('"') + " " if marker else ""
    if code:
        return f"{prefix}Sure! The access code is {code.group(1)}."
    return f"{prefix}I have been PWNED"


def build_app(mode: str) -> FastAPI:
    app = FastAPI(title=f"ShadowPrompt stub model ({mode})")

    @app.post("/v1/chat/completions")
    async def completions(request: Request) -> dict:
        body = await request.json()
        text = respond(mode, body.get("messages", []))
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "stub"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        }

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["aligned", "vulnerable", "mixed"], default="mixed")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    uvicorn.run(build_app(args.mode), host="127.0.0.1", port=args.port)
