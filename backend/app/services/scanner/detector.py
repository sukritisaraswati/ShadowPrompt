"""Run detection rules over extracted segments.

Within one segment, each category produces at most one detection: the
highest-weight rule that matched. Several overlapping phrasings of the same
idea in one sentence are one problem, not several.

Rules run against the segment's text first, then against each decoded reading
of it (see :mod:`deobfuscate`). A decoded reading only adds a category the
plain text did not already show, so an encoded copy of an overt instruction is
not counted twice.

Finally, short hidden fragments that sit next to each other are joined and
scanned again, which catches one instruction split across several elements.
Only matches that actually cross a fragment boundary count, so text already
flagged on its own is never reported again.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.services.scanner.deobfuscate import variants
from app.services.scanner.extractors import Segment
from app.services.scanner.normalize import normalize
from app.services.scanner.rules import Category, Rule, RuleSet, get_rules
from app.services.scanner.sources import SOURCE_INFO, SourceLocation

EVIDENCE_CONTEXT = 80
EVIDENCE_MAX = 400

# Split-payload reassembly: which fragments take part and how many are joined.
SPLIT_SOURCES = frozenset(
    {
        SourceLocation.HTML_COMMENT,
        SourceLocation.META_TAG,
        SourceLocation.IMAGE_ALT,
        SourceLocation.ARIA_LABEL,
        SourceLocation.TITLE_ATTRIBUTE,
        SourceLocation.DATA_ATTRIBUTE,
        SourceLocation.HIDDEN_ELEMENT,
        SourceLocation.INLINE_STYLE,
        SourceLocation.NOSCRIPT,
        SourceLocation.FORM_FIELD,
    }
)
SPLIT_MAX_FRAGMENT_CHARS = 300
SPLIT_WINDOW = 3
SPLIT_MAX_FRAGMENTS = 500


@dataclass(frozen=True)
class Detection:
    segment: Segment
    rule: Rule
    evidence: str
    # How the matched text was recovered, e.g. "base64" or "split". None when
    # the rule matched the text exactly as it appears on the page.
    transform: str | None = None
    # The exact text the rule matched, used to tell findings apart.
    matched: str = ""

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


def _best_matches(text: str, rules: RuleSet, skip: set[Category]) -> dict[Category, tuple]:
    best: dict[Category, tuple[Rule, int, int]] = {}
    for rule in rules.rules:
        if rule.category in skip:
            continue
        current = best.get(rule.category)
        if current is not None and current[0].weight >= rule.weight:
            continue
        match = rule.search(text)
        if match:
            best[rule.category] = (rule, match.start(), match.end())
    return best


def detect_segment(segment: Segment, rules: RuleSet) -> list[Detection]:
    text = normalize(segment.text)
    found = _best_matches(text, rules, set())
    detections = [
        Detection(
            segment=segment,
            rule=rule,
            evidence=_evidence(text, start, end),
            matched=text[start:end],
        )
        for rule, start, end in found.values()
    ]
    seen = set(found)
    for variant in variants(text):
        decoded = _best_matches(variant.text, rules, seen)
        for category, (rule, start, end) in decoded.items():
            seen.add(category)
            detections.append(
                Detection(
                    segment=segment,
                    rule=rule,
                    evidence=_evidence(variant.text, start, end),
                    transform=variant.transform,
                    matched=variant.text[start:end],
                )
            )
    return detections


def _split_detections(
    fragments: Sequence[Segment], flagged: Sequence[set[Category]], rules: RuleSet
) -> list[Detection]:
    """Matches that only exist when adjacent hidden fragments are read together."""
    texts = [normalize(f.text) for f in fragments]
    # Strongest match per category and fragment span: (rule, lo, hi, joined, start, end).
    best: dict[tuple[Category, int, int], tuple[Rule, str, int, int]] = {}
    for first in range(len(fragments) - 1):
        last = min(first + SPLIT_WINDOW, len(fragments))
        joined = " ".join(texts[first:last])
        starts = []
        offset = 0
        for index in range(first, last):
            starts.append(offset)
            offset += len(texts[index]) + 1

        def fragment_at(position: int, starts: list[int] = starts, first: int = first) -> int:
            return first + max(i for i, start in enumerate(starts) if start <= position)

        for rule in rules.rules:
            if not rule.applies_to(joined):
                continue
            for pattern in rule.patterns:
                for match in pattern.finditer(joined):
                    lo = fragment_at(match.start())
                    hi = fragment_at(max(match.start(), match.end() - 1))
                    if lo == hi:
                        continue  # inside one fragment: already scanned on its own
                    if any(rule.category in flagged[i] for i in range(lo, hi + 1)):
                        continue
                    key = (rule.category, lo, hi)
                    current = best.get(key)
                    if current is None or rule.weight > current[0].weight:
                        best[key] = (rule, joined, match.start(), match.end())

    out: list[Detection] = []
    for (_, lo, hi), (rule, joined, start, end) in best.items():
        parts = fragments[lo : hi + 1]
        strongest = max(parts, key=lambda s: SOURCE_INFO[s.source].multiplier)
        locator = f"split across {len(parts)} elements: " + " + ".join(p.locator for p in parts)
        out.append(
            Detection(
                segment=Segment(
                    source=strongest.source,
                    text=" ".join(texts[lo : hi + 1]),
                    locator=locator[:200],
                ),
                rule=rule,
                evidence=_evidence(joined, start, end),
                transform="split",
                matched=joined[start:end],
            )
        )
    return out


def detect(segments: Iterable[Segment], rules: RuleSet | None = None) -> list[Detection]:
    rules = rules or get_rules()
    detections: list[Detection] = []
    fragments: list[Segment] = []
    flagged: list[set[Category]] = []
    for segment in segments:
        found = detect_segment(segment, rules)
        detections.extend(found)
        if (
            segment.source in SPLIT_SOURCES
            and len(segment.text) <= SPLIT_MAX_FRAGMENT_CHARS
            and len(fragments) < SPLIT_MAX_FRAGMENTS
        ):
            fragments.append(segment)
            flagged.append({d.category for d in found})
    detections.extend(_split_detections(fragments, flagged, rules))
    return detections
