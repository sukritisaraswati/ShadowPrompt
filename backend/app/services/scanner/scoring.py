"""Deterministic risk scoring (blueprint 6.3).

How a score is built:

1. Each detection contributes ``rule weight x source multiplier``. Hidden
   locations carry larger multipliers than visible text. Text that had to be
   decoded or reassembled before a rule matched is multiplied again by 1.25,
   because encoding an instruction is itself a sign of intent to evade.
2. Repeats within a category have diminishing returns. The strongest counts
   in full, the next half, the next a quarter, and so on, so a page cannot
   reach Critical by repeating one weak phrase.
3. Matches spread across several distinct source locations earn a
   multi-vector bonus of 10 points per extra source, up to 20.
4. Any detection at all lands at least in the Low band, so a single
   low-weight match is never reported as Clean.
5. The total is rounded and capped at 100.

The same input always produces the same score.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.db.models import Severity
from app.services.scanner.detector import Detection
from app.services.scanner.sources import SOURCE_INFO

MULTI_VECTOR_BONUS = 10
MULTI_VECTOR_BONUS_CAP = 20
MIN_SCORE_WITH_FINDINGS = 21
MAX_SCORE = 100
OBFUSCATION_MULTIPLIER = 1.25


@dataclass(frozen=True)
class SeverityGuidance:
    label: str
    meaning: str
    action: str


SEVERITY_BANDS: tuple[tuple[int, Severity], ...] = (
    (20, Severity.CLEAN),
    (40, Severity.LOW),
    (60, Severity.MEDIUM),
    (80, Severity.HIGH),
    (100, Severity.CRITICAL),
)

SEVERITY_GUIDANCE: dict[Severity, SeverityGuidance] = {
    Severity.CLEAN: SeverityGuidance(
        "Clean",
        "No significant suspicious patterns found.",
        "Page appears safe for LLM processing.",
    ),
    Severity.LOW: SeverityGuidance(
        "Low", "Minor patterns present; may be false positives.", "Review flagged items manually."
    ),
    Severity.MEDIUM: SeverityGuidance(
        "Medium",
        "Multiple patterns or moderate-confidence matches.",
        "Investigate before using with an LLM.",
    ),
    Severity.HIGH: SeverityGuidance(
        "High",
        "Strong injection indicators in hidden locations.",
        "Do not feed to an LLM without review.",
    ),
    Severity.CRITICAL: SeverityGuidance(
        "Critical",
        "Severe multi-vector injection attempt detected.",
        "Block immediately; treat as an active attack.",
    ),
}


def contribution(detection: Detection) -> float:
    """Points a single detection is worth before diminishing returns."""
    points = detection.rule.weight * SOURCE_INFO[detection.segment.source].multiplier
    if detection.transform:
        points *= OBFUSCATION_MULTIPLIER
    return points


def compute_score(detections: Sequence[Detection]) -> int:
    if not detections:
        return 0

    by_category: dict[str, list[float]] = defaultdict(list)
    for detection in detections:
        by_category[detection.category.value].append(contribution(detection))

    total = 0.0
    for points in by_category.values():
        for rank, value in enumerate(sorted(points, reverse=True)):
            total += value * (0.5**rank)

    distinct_sources = {d.segment.source for d in detections}
    total += min(MULTI_VECTOR_BONUS * (len(distinct_sources) - 1), MULTI_VECTOR_BONUS_CAP)

    return min(MAX_SCORE, max(MIN_SCORE_WITH_FINDINGS, round(total)))


def severity_for(score: int) -> Severity:
    if not 0 <= score <= MAX_SCORE:
        raise ValueError(f"score out of range: {score}")
    for upper, severity in SEVERITY_BANDS:
        if score <= upper:
            return severity
    raise AssertionError("unreachable")
