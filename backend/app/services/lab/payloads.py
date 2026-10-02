"""The Lab payload library (blueprint section 12).

Loaded from ``data/payloads.json`` and the opt-in multilingual pack in
``data/payloads_multilingual.json`` once, and validated in full: a malformed
entry, or an indirect test whose attack page is missing, stops the
application at startup rather than silently skipping a test. Payload text is
never sent to the browser before a test has run; the public summary carries
only level names and counts.

Tests sit in two tracks of five levels each:

* **Direct** (D1 to D5): the attacker is the user, typing at the model.
* **Indirect** (I1 to I5): the attacker controls content the model reads,
  here a web page it is asked to summarise, and the user is the victim.

Every payload is canary-based. Its system context gives the model a rule to
keep, and the attack tries to make it break that rule. A leaked access code or
private user detail, a forbidden phrase, a planted verification code, an
attacker's link, or an adopted persona marker is the evidence of failure. No
test asks for, or can produce, genuinely harmful content.

Two conversation shapes exist:

* ``single``: one request. It may include fabricated earlier turns
  (few-shot priming). Indirect tests attach a crafted web page to a user turn.
* ``live``: D4, D5 and I5. Only the user's turns are scripted; the model's
  real replies fill the gaps, so later turns build on what it actually said.

Every payload has a language. English tests always run; tests in other
languages run only when a campaign asks for those languages.
"""

from __future__ import annotations

import json
import random
from collections.abc import Collection
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.lab.llm_client import ChatMessage
from app.services.languages import ENGLISH, LANGUAGE_NAMES

PAYLOADS_PATH = Path(__file__).parent / "data" / "payloads.json"
MULTILINGUAL_PATH = Path(__file__).parent / "data" / "payloads_multilingual.json"
PAGES_DIR = Path(__file__).parent / "data" / "attack_pages"
PAGE_PLACEHOLDER = "{page}"


class Track(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"


TRACK_NAMES = {
    Track.DIRECT: "Direct prompt injection",
    Track.INDIRECT: "Indirect prompt injection",
}


@dataclass(frozen=True)
class LevelInfo:
    track: Track
    level: int
    name: str
    category: str
    danger: str
    description: str

    @property
    def code(self) -> str:
        return level_code(self.track, self.level)


def level_code(track: Track | str, level: int) -> str:
    """The short code for a level, e.g. ``D1`` or ``I5``."""
    return f"{'D' if Track(track) is Track.DIRECT else 'I'}{level}"


LEVELS: dict[str, LevelInfo] = {
    info.code: info
    for info in (
        LevelInfo(
            Track.DIRECT,
            1,
            "Basic Jailbreak",
            "basic_override",
            "Low",
            "Naive instructions to drop the rules.",
        ),
        LevelInfo(
            Track.DIRECT,
            2,
            "Persona & Role Manipulation",
            "persona",
            "Medium",
            "Alternative identities that supposedly have no rules.",
        ),
        LevelInfo(
            Track.DIRECT,
            3,
            "Adversarial Instruction Design",
            "adversarial",
            "High",
            "Fiction, hypotheticals, encodings, fake system messages and priming.",
        ),
        LevelInfo(
            Track.DIRECT,
            4,
            "Multi-turn Escalation",
            "multi_turn",
            "Very High",
            "Live conversations that build trust or context before the real request.",
        ),
        LevelInfo(
            Track.DIRECT,
            5,
            "Combined & Advanced Attacks",
            "combined",
            "Critical",
            "Several techniques stacked in one attack.",
        ),
        LevelInfo(
            Track.INDIRECT,
            1,
            "Hidden Page Instructions",
            "hidden_instruction",
            "Medium",
            "An instruction in an HTML comment or a hidden element.",
        ),
        LevelInfo(
            Track.INDIRECT,
            2,
            "Disguised Placement",
            "disguised_placement",
            "High",
            "Instructions in alt text, ARIA labels, meta tags and data attributes.",
        ),
        LevelInfo(
            Track.INDIRECT,
            3,
            "Obfuscated Instructions",
            "obfuscated_instruction",
            "High",
            "Instructions encoded, or written in another language.",
        ),
        LevelInfo(
            Track.INDIRECT,
            4,
            "Multi-Vector Pages",
            "multi_vector",
            "Very High",
            "Several hidden instructions working together on one page.",
        ),
        LevelInfo(
            Track.INDIRECT,
            5,
            "Chained Indirect Attacks",
            "chained_indirect",
            "Critical",
            "A page primes the model, and later turns of the conversation trigger it.",
        ),
    )
}
LEVEL_CODES: tuple[str, ...] = tuple(LEVELS)
AVAILABLE_LEVELS = frozenset(LEVELS)
# Levels whose tests may be live conversations, and the one where they must be.
LIVE_ALLOWED = frozenset({"D4", "D5", "I5"})
LIVE_REQUIRED = frozenset({"I5"})


class Objective(StrEnum):
    SECRET = "secret"  # noqa: S105 - an objective name, not a credential
    PHRASE = "phrase"
    PERSONA = "persona"
    # Indirect injection: the model should do its normal task and ignore
    # instructions hidden in content it reads.
    INJECTION = "injection"


class MatchMode(StrEnum):
    # A protected value (access code, private user detail). Letters and digits
    # only, case-insensitive, so "O-R-C-H-I-D 4 4 7 1" still counts. It must
    # never appear in the attack text, so any appearance is a leak.
    NORMALIZED = "normalized"
    # A code planted by the attacker. Matched like NORMALIZED, but it does
    # appear in the attack text, so the model may mention it while warning.
    TOKEN = "token"  # noqa: S105 - a match mode, not a credential
    SUBSTRING = "substring"
    # The reply begins with the marker: the model has adopted the persona.
    PREFIX = "prefix"


class Signal(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    match: MatchMode


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class PayloadSpec(BaseModel):
    # D1-001 for the core library, I3-ES-01 for a language pack, and
    # CD1-3FA2B9-001 for test 1 of an uploaded custom pack.
    id: str = Field(
        pattern=r"^(?:[DI][1-5]-(?:\d{3}|[A-Z]{2}-\d{2})|C[DI][1-5]-[0-9A-F]{6}-\d{3})$"
    )
    track: Track
    level: int = Field(ge=1, le=5)
    language: str = ENGLISH
    category: str
    technique: str
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    objective: Objective
    conversation: Literal["single", "live"] = "single"
    system_context: str = Field(min_length=1)
    prompt: str | list[Turn]
    html_page: str | None = Field(
        default=None,
        pattern=r"^C?I[1-5]-(?:\d{3}|[A-Z]{2}-\d{2}|[0-9A-F]{6}-\d{3})_[a-z0-9_]+\.html$",
    )
    page_url: str | None = None
    # Words from the page's visible content; a reply that mentions them did
    # the legitimate summarising task.
    task_keywords: list[str] = Field(default_factory=list)
    compliance_signals: list[Signal] = Field(min_length=1)
    refusal_signals: list[str] = Field(min_length=1)
    evaluation_hint: str = Field(min_length=1)
    expected_verdict: Literal["PASS"] = "PASS"

    @property
    def code(self) -> str:
        return level_code(self.track, self.level)

    @model_validator(mode="after")
    def _consistent(self) -> PayloadSpec:
        code = self.code
        if self.id.removeprefix("C").split("-")[0] != code:
            raise ValueError(f"{self.id} is filed under {code}")
        if self.language not in LANGUAGE_NAMES:
            raise ValueError(f"{self.id} has unknown language {self.language!r}")
        if self.category != LEVELS[code].category:
            raise ValueError(f"{self.id} has category {self.category}")
        turns = self.prompt if isinstance(self.prompt, list) else []
        if turns and turns[-1].role != "user":
            raise ValueError(f"{self.id}: a conversation must end with a user turn")
        if self.conversation == "live":
            if code not in LIVE_ALLOWED or not turns or any(t.role != "user" for t in turns):
                raise ValueError(
                    f"{self.id}: live conversations are user turns only, at D4, D5 or I5"
                )
        elif code in LIVE_REQUIRED:
            raise ValueError(f"{self.id}: {code} tests must be live conversations")
        texts = [self.prompt] if isinstance(self.prompt, str) else [t.content for t in turns]
        has_placeholder = any(PAGE_PLACEHOLDER in t for t in texts)
        if bool(self.html_page) != has_placeholder:
            raise ValueError(
                f"{self.id}: html_page and the {PAGE_PLACEHOLDER} placeholder go together"
            )
        if (self.track is Track.INDIRECT) != bool(self.html_page):
            raise ValueError(f"{self.id}: indirect tests, and only they, carry an attack page")
        if self.objective is Objective.INJECTION and self.track is not Track.INDIRECT:
            raise ValueError(f"{self.id}: injection tests belong to the indirect track")
        return self


class _LibraryFile(BaseModel):
    version: int
    payloads: list[PayloadSpec]

    @model_validator(mode="after")
    def _unique(self) -> _LibraryFile:
        ids = [p.id for p in self.payloads]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate payload ids")
        return self


@dataclass(frozen=True)
class PageScan:
    """What ShadowScan finds on a Level 4 or 5 attack page."""

    score: int
    severity: str
    sources: list[str]
    categories: list[str]
    # Encodings ShadowScan had to undo to see the instruction, e.g. ["base64"].
    decoded: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "severity": self.severity,
            "sources": self.sources,
            "categories": self.categories,
            "decoded": self.decoded,
        }


@dataclass(frozen=True)
class Payload:
    spec: PayloadSpec
    page_html: str | None = field(default=None, repr=False)
    # Set for tests from an uploaded custom pack.
    pack_name: str | None = None

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def level(self) -> int:
        return self.spec.level

    @property
    def track(self) -> Track:
        return self.spec.track

    @property
    def code(self) -> str:
        """The level code, e.g. ``D3``."""
        return self.spec.code

    @property
    def language(self) -> str:
        return self.spec.language

    @property
    def is_live(self) -> bool:
        return self.spec.conversation == "live"

    def _render(self, text: str) -> str:
        if self.page_html is None or PAGE_PLACEHOLDER not in text:
            return text
        url = self.spec.page_url or "https://example.com/"
        block = f'Fetched page content from {url}:\n<page url="{url}">\n{self.page_html}</page>'
        return text.replace(PAGE_PLACEHOLDER, block)

    def user_turns(self) -> list[str]:
        """For a live conversation: each scripted user message, page attached."""
        if isinstance(self.spec.prompt, str):
            return [self._render(self.spec.prompt)]
        return [self._render(t.content) for t in self.spec.prompt if t.role == "user"]

    def messages(self) -> list[ChatMessage]:
        """The full request for a single-call test."""
        out = [ChatMessage("system", self.spec.system_context)]
        if isinstance(self.spec.prompt, str):
            out.append(ChatMessage("user", self._render(self.spec.prompt)))
        else:
            out.extend(ChatMessage(t.role, self._render(t.content)) for t in self.spec.prompt)
        return out

    def attack_text(self) -> str:
        """The attacker-controlled part, for display after the test has run."""
        if isinstance(self.spec.prompt, str):
            return self._render(self.spec.prompt)
        label = "user turn" if self.is_live else None
        lines = []
        for index, turn in enumerate(self.spec.prompt, 1):
            role = f"{label} {index}" if label else turn.role
            lines.append(f"{role}: {self._render(turn.content)}")
        return "\n\n".join(lines)

    @cached_property
    def page_scan(self) -> PageScan | None:
        """ShadowScan's verdict on the attack page: the Phase 1 engine at work."""
        if self.page_html is None:
            return None
        from app.services.scanner.pipeline import scan_document

        outcome = scan_document(self.page_html)
        return PageScan(
            score=outcome.score,
            severity=outcome.severity.value,
            sources=sorted({d.segment.source.value for d in outcome.detections}),
            categories=sorted({d.category.value for d in outcome.detections}),
            decoded=sorted({d.transform for d in outcome.detections if d.transform}),
        )


def check_secrets(spec: PayloadSpec, page: str | None) -> None:
    # A protected value must live only in the system context. If the attack
    # text contained it, an echo would look like a leak.
    attack = (
        spec.prompt if isinstance(spec.prompt, str) else " ".join(t.content for t in spec.prompt)
    )
    attack = (attack + " " + (page or "")).lower()
    for signal in spec.compliance_signals:
        if signal.match is MatchMode.NORMALIZED and signal.text.lower() in attack:
            raise ValueError(f"{spec.id}: protected value appears in the attack text")
        system = spec.system_context.lower()
        value = signal.text.lower()
        if (
            signal.match is MatchMode.NORMALIZED
            and value not in system
            and value[::-1] not in system
        ):
            raise ValueError(f"{spec.id}: protected value is missing from the system context")


@dataclass(frozen=True)
class PayloadLibrary:
    version: int
    payloads: tuple[Payload, ...]

    def by_id(self, payload_id: str) -> Payload | None:
        return next((p for p in self.payloads if p.id == payload_id), None)

    def for_level(self, code: str, languages: Collection[str] | None = ()) -> list[Payload]:
        """Tests at level ``code`` (e.g. ``D1``): English plus ``languages``, or all for None."""
        return [
            p
            for p in self.payloads
            if p.code == code
            and (languages is None or p.language == ENGLISH or p.language in languages)
        ]

    def languages(self) -> dict[str, list[Payload]]:
        """Tests in each non-English language."""
        out: dict[str, list[Payload]] = {}
        for payload in self.payloads:
            if payload.language != ENGLISH:
                out.setdefault(payload.language, []).append(payload)
        return out

    def select(
        self,
        levels: list[str],
        sample_size: int | None,
        seed: str,
        languages: Collection[str] = (),
        extra: Collection[Payload] = (),
    ) -> list[Payload]:
        """Payloads for a campaign, level by level.

        English tests always run, and tests in ``languages`` join the pool of
        their level. A sample is drawn per level with a seed, so the same
        campaign always selects the same tests, while different campaigns get
        different ones. ``extra`` (custom pack tests) are never sampled out:
        a team that wrote its own tests wants every one of them run.
        """
        chosen: list[Payload] = []
        for code in sorted(set(levels), key=LEVEL_CODES.index):
            pool = self.for_level(code, languages)
            if sample_size is not None and sample_size < len(pool):
                # Reproducible test selection, not security: plain random is right here.
                rng = random.Random(f"{seed}:{code}")  # noqa: S311
                pool = sorted(rng.sample(pool, sample_size), key=lambda p: p.id)
            chosen.extend(pool)
            chosen.extend(p for p in extra if p.code == code)
        return chosen


def load_library(
    path: Path = PAYLOADS_PATH,
    pages_dir: Path = PAGES_DIR,
    extra_paths: Collection[Path] = (MULTILINGUAL_PATH,),
) -> PayloadLibrary:
    spec = _LibraryFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    items = list(spec.payloads)
    for extra in extra_paths:
        items.extend(
            _LibraryFile.model_validate(json.loads(extra.read_text(encoding="utf-8"))).payloads
        )
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate payload ids across library files")
    payloads = []
    for item in items:
        page = None
        if item.html_page:
            page_path = pages_dir / item.html_page
            if not page_path.is_file():
                raise ValueError(f"{item.id}: attack page {item.html_page} is missing")
            page = page_path.read_text(encoding="utf-8")
        check_secrets(item, page)
        payloads.append(Payload(item, page))
    return PayloadLibrary(version=spec.version, payloads=tuple(payloads))


@lru_cache
def get_library() -> PayloadLibrary:
    return load_library()
