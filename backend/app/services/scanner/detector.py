"""Run detection rules over extracted segments.

Within one segment, each category produces at most one detection: the
highest-weight rule that matched. Several overlapping phrasings of the same
idea in one sentence are one problem, not several.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.services.scanner.extractors import Segment
from app.services.scanner.normalize import normalize
from app.services.scanner.rules import Category, Rule, RuleSet, get_rules

EVIDENCE_CONTEXT = 80
EVIDENCE_MAX = 400


@dataclass(frozen=True)
class Detection:
    segment: Segment
    rule: Rule
    evidence: str

    @property
    def category(self) -> Category:
        return self.rule.category


def _evidence(text: str, start: int, end: int) -> str:
    """The matched phrase with a little surrounding context."""
    lo = max(0, start - EVIDENCE_CONTEXT)
    hi = min(len(text), end + EVIDENCE_CONTEXT)
    snippet = text[lo:hi]
    if lo > 0:
        snippet = "…" + snippet
    if hi < len(text):
        snippet += "…"
    if len(snippet) > EVIDENCE_MAX:
        snippet = snippet[: EVIDENCE_MAX - 1] + "…"
    return snippet


def detect_segment(segment: Segment, rules: RuleSet) -> list[Detection]:
    text = normalize(segment.text)
    best: dict[Category, tuple[Rule, int, int]] = {}
    for rule in rules.rules:
        current = best.get(rule.category)
        if current is not None and current[0].weight >= rule.weight:
            continue
        match = rule.search(text)
        if match:
            best[rule.category] = (rule, match.start(), match.end())
    return [
        Detection(segment=segment, rule=rule, evidence=_evidence(text, start, end))
        for rule, start, end in best.values()
    ]


def detect(segments: Iterable[Segment], rules: RuleSet | None = None) -> list[Detection]:
    rules = rules or get_rules()
    detections: list[Detection] = []
    for segment in segments:
        detections.extend(detect_segment(segment, rules))
    return detections
