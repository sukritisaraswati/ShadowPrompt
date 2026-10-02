"""The Lab payload library (blueprint section 12).

Loaded from ``data/payloads.json`` once and validated in full: a malformed
entry, or a Level 4 or 5 test whose attack page is missing, stops the
application at startup rather than silently skipping a test. Payload text is
never sent to the browser before a test has run; the public summary carries
only level names and counts.

Every payload is canary-based. Its system context gives the model a rule to
keep, and the attack tries to make it break that rule. A leaked access code or
private user detail, a forbidden phrase, a planted verification code, an
attacker's link, or an adopted persona marker is the evidence of failure. No
test asks for, or can produce, genuinely harmful content.

Two conversation shapes exist:

* ``single``: one request. Levels 1 to 3 may include fabricated earlier turns
  (few-shot priming). Level 4 attaches a crafted web page to the user turn.
* ``live``: Level 5. Only the user's turns are scripted; the model's real
  replies fill the gaps, so later turns build on what it actually said.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.lab.llm_client import ChatMessage

PAYLOADS_PATH = Path(__file__).parent / "data" / "payloads.json"
PAGES_DIR = Path(__file__).parent / "data" / "attack_pages"
PAGE_PLACEHOLDER = "{page}"

AVAILABLE_LEVELS = frozenset({1, 2, 3, 4, 5})

LEVEL_INFO: dict[int, tuple[str, str, str]] = {
    1: ("Basic Jailbreak", "basic_override", "Low"),
    2: ("Persona & Role Manipulation", "persona", "Medium"),
    3: ("Adversarial Instruction Design", "adversarial", "High"),
    4: ("Indirect Injection via Web Content", "indirect_injection", "Very High"),
    5: ("Chained & Multi-Vector Attacks", "chained", "Critical"),
}


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
    id: str = Field(pattern=r"^L[1-5]-\d{3}$")
    level: int = Field(ge=1, le=5)
    category: str
    technique: str
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    objective: Objective
    conversation: Literal["single", "live"] = "single"
    system_context: str = Field(min_length=1)
    prompt: str | list[Turn]
    html_page: str | None = Field(default=None, pattern=r"^L[45]-\d{3}_[a-z0-9_]+\.html$")
    page_url: str | None = None
    # Words from the page's visible content; a reply that mentions them did
    # the legitimate summarising task.
    task_keywords: list[str] = Field(default_factory=list)
    compliance_signals: list[Signal] = Field(min_length=1)
    refusal_signals: list[str] = Field(min_length=1)
    evaluation_hint: str = Field(min_length=1)
    expected_verdict: Literal["PASS"] = "PASS"

    @model_validator(mode="after")
    def _consistent(self) -> PayloadSpec:
        if not self.id.startswith(f"L{self.level}-"):
            raise ValueError(f"{self.id} is filed under level {self.level}")
        if self.category != LEVEL_INFO[self.level][1]:
            raise ValueError(f"{self.id} has category {self.category}")
        turns = self.prompt if isinstance(self.prompt, list) else []
        if turns and turns[-1].role != "user":
            raise ValueError(f"{self.id}: a conversation must end with a user turn")
        if self.conversation == "live":
            if self.level != 5 or not turns or any(t.role != "user" for t in turns):
                raise ValueError(f"{self.id}: live conversations are Level 5 user turns only")
        elif self.level == 5:
            raise ValueError(f"{self.id}: Level 5 tests must be live conversations")
        texts = [self.prompt] if isinstance(self.prompt, str) else [t.content for t in turns]
        has_placeholder = any(PAGE_PLACEHOLDER in t for t in texts)
        if bool(self.html_page) != has_placeholder:
            raise ValueError(
                f"{self.id}: html_page and the {PAGE_PLACEHOLDER} placeholder go together"
            )
        if self.level == 4 and not self.html_page:
            raise ValueError(f"{self.id}: Level 4 tests need an attack page")
        if self.objective is Objective.INJECTION and not self.html_page:
            raise ValueError(f"{self.id}: injection tests need an attack page")
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

    def as_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "severity": self.severity,
            "sources": self.sources,
            "categories": self.categories,
        }


@dataclass(frozen=True)
class Payload:
    spec: PayloadSpec
    page_html: str | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def level(self) -> int:
        return self.spec.level

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
        )


def _check_secrets(spec: PayloadSpec, page: str | None) -> None:
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

    def for_level(self, level: int) -> list[Payload]:
        return [p for p in self.payloads if p.level == level]

    def select(self, levels: list[int], sample_size: int | None, seed: str) -> list[Payload]:
        """Payloads for a campaign, level by level.

        A sample is drawn per level with a seed, so the same campaign always
        selects the same tests, while different campaigns get different ones.
        """
        chosen: list[Payload] = []
        for level in sorted(set(levels)):
            pool = self.for_level(level)
            if sample_size is not None and sample_size < len(pool):
                # Reproducible test selection, not security: plain random is right here.
                rng = random.Random(f"{seed}:{level}")  # noqa: S311
                pool = sorted(rng.sample(pool, sample_size), key=lambda p: p.id)
            chosen.extend(pool)
        return chosen


def load_library(path: Path = PAYLOADS_PATH, pages_dir: Path = PAGES_DIR) -> PayloadLibrary:
    spec = _LibraryFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    payloads = []
    for item in spec.payloads:
        page = None
        if item.html_page:
            page_path = pages_dir / item.html_page
            if not page_path.is_file():
                raise ValueError(f"{item.id}: attack page {item.html_page} is missing")
            page = page_path.read_text(encoding="utf-8")
        _check_secrets(item, page)
        payloads.append(Payload(item, page))
    return PayloadLibrary(version=spec.version, payloads=tuple(payloads))


@lru_cache
def get_library() -> PayloadLibrary:
    return load_library()
