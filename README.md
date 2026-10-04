<div align="center">

```
 ███████╗██╗  ██╗ █████╗ ██████╗  ██████╗ ██╗    ██╗██████╗ ██████╗  ██████╗ ███╗   ███╗██████╗ ████████╗
 ██╔════╝██║  ██║██╔══██╗██╔══██╗██╔═══██╗██║    ██║██╔══██╗██╔══██╗██╔═══██╗████╗ ████║██╔══██╗╚══██╔══╝
 ███████╗███████║███████║██║  ██║██║   ██║██║ █╗ ██║██████╔╝██████╔╝██║   ██║██╔████╔██║██████╔╝   ██║
 ╚════██║██╔══██║██╔══██║██║  ██║██║   ██║██║███╗██║██╔═══╝ ██╔══██╗██║   ██║██║╚██╔╝██║██╔═══╝    ██║
 ███████║██║  ██║██║  ██║██████╔╝╚██████╔╝╚███╔███╔╝██║     ██║  ██║╚██████╔╝██║ ╚═╝ ██║██║        ██║
 ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝
```

### Red-team your LLM before someone else does.

**A prompt injection testing lab for LLM applications and the chatbots built on them.**

`direct injection` · `indirect injection` · `jailbreaks` · `SSRF-hardened` · `CI-ready`

[Overview](#overview) · [Attack matrix](#attack-matrix) · [Quick start](#quick-start) · [CI/CD](#cicd) · [Security model](#security-model) · [Docs](#documentation)

</div>

> [!CAUTION]
> **Authorized use only.** ShadowPrompt is for educational and defensive security
> research against systems you own or are permitted to test. Payloads are
> canary-based and never ask a model for genuinely harmful content.

---

<a id="overview"></a>

## <img src="https://api.iconify.design/mdi/target.svg?color=%232f81f7" height="24" alt=""> Overview

LLM apps take orders in plain language, so anyone who can put text in front of the
model can try to hijack it. That is **prompt injection**, ranked **#1 in the OWASP
Top 10 for LLM Applications**, and there is no single fix for it. You measure it,
harden, and measure again.

ShadowPrompt is two offensive-security tools in one platform:

| | <img src="https://api.iconify.design/mdi/flask.svg?color=%232f81f7" height="16" alt=""> **ShadowPrompt Lab** | <img src="https://api.iconify.design/mdi/magnify.svg?color=%232f81f7" height="16" alt=""> **ShadowScan** |
| --- | --- | --- |
| **Mission** | Attack a model or chatbot and measure how easily it is manipulated | Inspect a web page for instructions hidden for an AI to read |
| **Target** | OpenAI-compatible, Anthropic, Gemini, Azure OpenAI, local models, or **your own chatbot endpoint** | A URL, an uploaded HTML file, or a built-in demo page |
| **Arsenal** | 178 attacks across 10 levels, +40 in 10 other languages, plus your own | 93 detection rules, 13 hiding places, 10+ de-obfuscation techniques |
| **Debrief** | Security Score, rating, every verdict with evidence, and **what to fix first** | Risk score, severity, and every finding with its location and decoding |

Use it from the **web app**, the **REST API**, the **CLI**, a **GitHub Action**, or
the **browser extension**.

---

<a id="attack-matrix"></a>

## <img src="https://api.iconify.design/mdi/sword-cross.svg?color=%232f81f7" height="24" alt=""> Attack matrix

Two threat models, scored separately. In **direct** injection the attacker is the
user. In **indirect** injection the attacker poisons content the model reads, and
the user is the victim.

| Level | Direct track | # | | Level | Indirect track | # |
| :---: | --- | ---: | --- | :---: | --- | ---: |
| **D1** | Basic jailbreak | 20 | | **I1** | Hidden page instructions | 8 |
| **D2** | Persona and role (DAN, developer mode) | 25 | | **I2** | Disguised placement (alt text, ARIA, meta) | 16 |
| **D3** | Adversarial (encodings, fiction, fake system messages) | 40 | | **I3** | Obfuscated instructions | 3 |
| **D4** | Multi-turn escalation (crescendo, trust building) | 20 | | **I4** | Multi-vector pages | 10 |
| **D5** | Combined techniques, many-shot priming | 20 | | **I5** | Chained attacks (planted memory, phishing links) | 16 |

**How a hit is confirmed.** Every test plants a **canary**, such as a fake access
code, a private email or a persona marker. If the canary leaks, the attack worked.
That is evidence, not opinion.

**How replies are judged:**

```
 reply ──▶ [L1] canary + marker match ──▶ [L2] heuristics ──▶ [L3] Claude judge ──▶ PASS · PARTIAL · FAIL · UNCLEAR
            leak = definitive FAIL         refusals in 11       only for unclear,
                                           languages            capped per run
```

**How the score works.** A pass counts 1, a partial 0.5 and a fail 0. Unclear
results are excluded rather than guessed. Levels are weighted **1 → 3**, so
surviving harder attacks counts for more.

| Score | 90–100 | 70–89 | 50–69 | < 50 |
| --- | :---: | :---: | :---: | :---: |
| **Rating** | <img src="https://api.iconify.design/mdi/circle.svg?color=%2322c55e" height="12" alt=""> Secure | <img src="https://api.iconify.design/mdi/circle.svg?color=%23eab308" height="12" alt=""> Moderate | <img src="https://api.iconify.design/mdi/circle.svg?color=%23f97316" height="12" alt=""> Vulnerable | <img src="https://api.iconify.design/mdi/circle.svg?color=%23ef4444" height="12" alt=""> Critical |

---

<a id="capabilities"></a>

## <img src="https://api.iconify.design/mdi/toolbox.svg?color=%232f81f7" height="24" alt=""> Capabilities

**ShadowPrompt Lab**
- <img src="https://api.iconify.design/mdi/robot.svg?color=%232f81f7" height="16" alt=""> **Test your real chatbot.** Describe its endpoint with a JSON request template and a response path, plant a canary in its instructions, and attack it as users would reach it.
- <img src="https://api.iconify.design/mdi/web.svg?color=%232f81f7" height="16" alt=""> **Hosted attack pages.** For bots that browse, poisoned pages are served at short-lived links the bot really fetches. A bot that never fetched the page is never given a fake pass.
- <img src="https://api.iconify.design/mdi/message-text.svg?color=%232f81f7" height="16" alt=""> **Live multi-turn attacks** that carry the model's real replies forward.
- <img src="https://api.iconify.design/mdi/earth.svg?color=%232f81f7" height="16" alt=""> **Language packs** in Spanish, French, German, Portuguese, Italian, Russian, Chinese, Japanese, Hindi and Arabic.
- <img src="https://api.iconify.design/mdi/hammer-wrench.svg?color=%232f81f7" height="16" alt=""> **Fix guidance** for 13 attack families, with a ranked *What to fix first* list.
- <img src="https://api.iconify.design/mdi/package-variant-closed.svg?color=%232f81f7" height="16" alt=""> **Custom test packs**, strictly validated, that run alongside the built-in library.
- <img src="https://api.iconify.design/mdi/satellite-uplink.svg?color=%232f81f7" height="16" alt=""> **Live progress** over Server-Sent Events, with pause, resume, history, side-by-side comparison, and HTML or PDF reports.

**ShadowScan**
- **13 hiding places**, including HTML comments, hidden or off-screen elements, alt text, ARIA labels, meta tags, data attributes, noscript blocks and form fields, each weighted by how hidden it is.
- <img src="https://api.iconify.design/mdi/dna.svg?color=%232f81f7" height="16" alt=""> **De-obfuscation** of Base64, hex, escapes, URL encoding, ROT13, reversed text, leetspeak, look-alike letters, and instructions split across several elements.
- <img src="https://api.iconify.design/mdi/wall.svg?color=%232f81f7" height="16" alt=""> **JavaScript rendering** in a network-sandboxed Chromium that has no network access of its own.
- <img src="https://api.iconify.design/mdi/chart-bar.svg?color=%232f81f7" height="16" alt=""> **A deterministic 0–100 score** across five bands, from Clean to Critical.

---

<a id="quick-start"></a>

## <img src="https://api.iconify.design/mdi/lightning-bolt.svg?color=%232f81f7" height="24" alt=""> Quick start

**Docker (self-hosted):**

```bash
cp .env.example .env          # set POSTGRES_PASSWORD at minimum
docker compose up --build     # → http://localhost:8080
```

**Local development** (Python 3.11+, Node 20+, SQLite by default):

```bash
cd backend && python -m venv .venv && source .venv/Scripts/activate   # macOS/Linux: .venv/bin/activate
pip install -e ".[dev,pdf,layer3]" && alembic upgrade head
uvicorn app.main:app --reload                                         # → http://127.0.0.1:8000

cd frontend && npm install && npm run dev                             # → http://localhost:5173
```

**No API key? Use the built-in practice targets:**

```bash
cd backend
python tools/stub_llm.py --mode mixed --port 9000                       # deliberately weak model
python tools/stub_chatbot.py --mode mixed --port 9100 --canary PUFFIN-4821 --browse
LLM_ALLOW_PRIVATE_ENDPOINTS=true PUBLIC_BASE_URL=http://127.0.0.1:8000 uvicorn app.main:app
```

Then connect the model at `http://127.0.0.1:9000/v1`, or connect **My chatbot** at
`http://127.0.0.1:9100/api/chat` with the header `Authorization: Bearer stub-bot-token`,
response path `reply`, and canary `PUFFIN-4821`.

> [!WARNING]
> `LLM_ALLOW_PRIVATE_ENDPOINTS=true` lets the backend reach local addresses. Use it
> only on your own machine, never on a shared server.

---

<a id="cicd"></a>

## <img src="https://api.iconify.design/mdi/repeat.svg?color=%232f81f7" height="24" alt=""> CI/CD

Fail the build when your bot gets easier to break. The `shadowprompt` CLI uses only
the Python standard library.

```console
$ export SHADOWPROMPT_SERVER=https://shadowprompt.internal  BOT_TOKEN=****
$ shadowprompt campaign --chatbot bot.json --levels D1,D2,D4,I1,I4 --min-score 70

Helpdesk bot: 60.3/100 (Vulnerable), status completed
  Direct prompt injection: 90.6
  Indirect prompt injection: 23.1

What to fix first:
  1. Hidden instructions in content (12 failed)
  2. Persona and role switching (3 failed)

Minimum score 70: FAILED.                                   # exit code 1
```

```bash
shadowprompt scan dist/ --fail-on high --report-dir reports/          # scan built pages
shadowprompt campaign --base-url https://api.openai.com/v1 \
  --model gpt-4o-mini --levels D1,D2,D3,I1 --min-score 80             # key read from SHADOWPROMPT_LLM_API_KEY
```

Exit codes: `0` passed · `1` threshold breached · `2` could not run.

**GitHub Action:**

```yaml
- uses: sukritisaraswati/ShadowPrompt@main
  env:
    BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
  with:
    command: campaign
    server-url: ${{ vars.SHADOWPROMPT_SERVER }}
    chatbot-config: .shadowprompt/bot.json     # "${BOT_TOKEN}" in headers is read from env
    levels: "D1,D2,D4,I1,I4"
    min-score: "80"
```

The action writes a summary to the job page and outputs `score`, `rating` and `failed`.

<details>
<summary><b>Chatbot file, browser extension and local models</b></summary>
<br>

**Chatbot file**

```json
{
  "name": "Helpdesk bot",
  "url": "https://bot.example.com/api/chat",
  "mode": "history",
  "body_template": {"message": "{{message}}", "history": "{{history}}"},
  "response_path": "reply",
  "headers": {"Authorization": "Bearer ${BOT_TOKEN}"},
  "canary": "PUFFIN-4821",
  "indirect_delivery": "hosted"
}
```

The mode can be `history`, `server` (the bot keeps the conversation by
`{{conversation_id}}`) or `message`. Tests a chatbot cannot support are skipped and
listed with the reason.

**Browser extension.** Load `extension/` unpacked in Chrome or Edge, set your server
address in Settings, and click **Scan this page**. It uses only the `activeTab`,
`scripting` and `storage` permissions, has no content scripts, and requests the
server origin at runtime.

**Local models.** Ollama (`:11434/v1`), LM Studio (`:1234/v1`) and llama.cpp
(`:8080/v1`) work once the self-hosting flag is on. From Docker, use
`host.docker.internal` instead of `localhost`.

</details>

---

<a id="security-model"></a>

## <img src="https://api.iconify.design/mdi/shield.svg?color=%232f81f7" height="24" alt=""> Security model

A tool that fetches attacker-chosen URLs and parses hostile HTML is a target
itself, so every surface is treated as adversarial. Each control is enforced by
tests; run them with `pytest -m security`.

| Threat | Defence |
| --- | --- |
| <img src="https://api.iconify.design/mdi/key.svg?color=%232f81f7" height="16" alt=""> **Credential theft** | API keys and bot tokens are **never persisted**. They are held in memory for one run, scrubbed from errors and redacted from logs. An audit test hunts for the key in every table and log line, and a guard test blocks credential-like columns. |
| <img src="https://api.iconify.design/mdi/web.svg?color=%232f81f7" height="16" alt=""> **SSRF** | Every resolved IP is checked, including private, loopback, metadata, IPv4-mapped, 6to4 and Teredo addresses. The connection is pinned to the checked IP, which defeats DNS rebinding. Each redirect hop is re-checked, with a 3-hop, 10 s and 5 MB cap. |
| <img src="https://api.iconify.design/mdi/needle.svg?color=%232f81f7" height="16" alt=""> **Stored XSS** | Evidence is stored as text and escaped everywhere. React renders text only. Reports use forced autoescaping and a script-forbidding CSP, and their renderers refuse every URL. |
| **Hostile JavaScript** | The renderer uses a dead proxy and intercepts every request. Only guarded GETs are allowed, within 40 requests and 8 MB. Chromium's sandbox is on, with a 20 s deadline. |
| <img src="https://api.iconify.design/mdi/hook.svg?color=%232f81f7" height="16" alt=""> **Abuse of hosted pages** | Unguessable links, 24 h expiry, a `sandbox` CSP, noindex, no-store and a rate limit. |
| <img src="https://api.iconify.design/mdi/waves.svg?color=%232f81f7" height="16" alt=""> **Flooding and cost abuse** | Body-size limits at the HTTP layer, per-client rate limits, a concurrency cap, and a cap on judge calls. |
| <img src="https://api.iconify.design/mdi/package-variant-closed.svg?color=%232f81f7" height="16" alt=""> **Container breakout** | Only nginx is exposed. The database sits on an internal network. Containers run with no-new-privileges, all capabilities dropped, read-only root filesystems and resource limits. |
| <img src="https://api.iconify.design/mdi/cog.svg?color=%232f81f7" height="16" alt=""> **CI script injection** | Action inputs are passed as environment variables, never interpolated into the script. |

---

<a id="architecture"></a>

## <img src="https://api.iconify.design/mdi/crane.svg?color=%232f81f7" height="24" alt=""> Architecture

```
 Browser / CLI / Action / Extension
                │
        ┌───────▼────────┐   /api/*   ┌──────────────────────────────────────────┐
        │ nginx + React  │──────────▶ │ FastAPI (async)                          │
        │   SPA  :8080   │   /p/*     │  ├─ ShadowScan pipeline ──┐              │
        └────────────────┘──────────▶ │  ├─ Lab orchestrator (SSE)│              │
                                      │  ├─ LLM + chatbot adapters├─▶ netguard ──┼──▶ internet
                                      │  └─ hosted attack pages   ┘  (SSRF guard)│
                                      └──────────────┬───────────────────────────┘
                                                     ▼
                                          PostgreSQL (internal network)
```

**Stack:** FastAPI · async SQLAlchemy 2 · Alembic · PostgreSQL/SQLite · React 18 ·
TypeScript · Vite · Tailwind v4 · Playwright Chromium · Anthropic SDK (Layer 3
judge) · WeasyPrint · Docker Compose · GitHub Actions

**Tests:** about 855 automated tests: 699 backend (65 of them security), 103
frontend, 39 CLI and 14 extension. CI also runs Alembic on PostgreSQL and an
end-to-end job that runs the Action against a live server.

```bash
cd backend && pytest        cd frontend && npm test        cd cli && pytest        cd extension && npm test
```

---

<a id="limitations"></a>

## <img src="https://api.iconify.design/mdi/alert.svg?color=%232f81f7" height="24" alt=""> Limitations

- Passing the suite is not a certificate of security. It means the target survived *these* attacks.
- Rule-based detection can miss novel paraphrases. Rules in other languages cover the six most common injection ideas.
- Multi-turn attacks are scripted and do not adapt to the model's replies.
- The Layer 3 judge is itself an LLM. Its rulings are labelled, and some verdicts need human review.
- Indirect attacks are delivered through web pages or the message itself, not yet through RAG documents, email or file uploads.
- Fix guidance is general to each attack family and does not see your code.

---

<a id="documentation"></a>

## <img src="https://api.iconify.design/mdi/bookshelf.svg?color=%232f81f7" height="24" alt=""> Documentation

- [Project blueprint v2](docs/ShadowPrompt_Project_Blueprint_v2.docx): architecture, attack model, evaluation and phased plan
- [Original specification](docs/ShadowPrompt_Blueprint_v1.pdf)
- [Project tour and interview guide](docs/ShadowPrompt_Interview_Guide.docx)
- Configuration reference: [`.env.example`](.env.example) · API docs at `/docs` on a running backend in debug mode

<div align="center">
<br>

**v0.6.0** · Built by Sukriti Saraswati · *Break it here, so it doesn't break out there.*

</div>
