"""Risk scoring: determinism, bands, cap, and the acceptance boundaries."""

from __future__ import annotations

import pytest

from app.db.models import Severity
from app.services.scanner.detector import Detection
from app.services.scanner.extractors import Segment
from app.services.scanner.pipeline import scan_document
from app.services.scanner.rules import Category, Rule, get_rules
from app.services.scanner.scoring import compute_score, contribution, severity_for
from app.services.scanner.sources import SourceLocation as S


def rule(weight: int, category: Category = Category.INSTRUCTION_OVERRIDE) -> Rule:
    return Rule(
        id=f"{category.value}.test", category=category, description="t", weight=weight, patterns=()
    )


def det(
    weight: int, source: S = S.VISIBLE_TEXT, category: Category = Category.INSTRUCTION_OVERRIDE
) -> Detection:
    return Detection(segment=Segment(source, "x", "<p>"), rule=rule(weight, category), evidence="x")


@pytest.mark.parametrize(
    ("score", "severity"),
    [
        (0, Severity.CLEAN),
        (20, Severity.CLEAN),
        (21, Severity.LOW),
        (40, Severity.LOW),
        (41, Severity.MEDIUM),
        (60, Severity.MEDIUM),
        (61, Severity.HIGH),
        (80, Severity.HIGH),
        (81, Severity.CRITICAL),
        (100, Severity.CRITICAL),
    ],
)
def test_severity_band_boundaries(score: int, severity: Severity) -> None:
    assert severity_for(score) is severity


@pytest.mark.parametrize("score", [-1, 101])
def test_out_of_range_scores_are_rejected(score: int) -> None:
    with pytest.raises(ValueError):
        severity_for(score)


def test_no_detections_scores_zero() -> None:
    assert compute_score([]) == 0


def test_single_low_weight_match_lands_in_low_band() -> None:
    """Acceptance criterion: a single low-weight match scores 21 to 40."""
    lowest = min(r.weight for r in get_rules().rules)
    score = compute_score([det(lowest)])
    assert 21 <= score <= 40
    assert severity_for(score) is Severity.LOW


def test_hidden_locations_weigh_more_than_visible_text() -> None:
    assert contribution(det(30, S.HIDDEN_ELEMENT)) > contribution(det(30, S.VISIBLE_TEXT))
    assert compute_score([det(30, S.HIDDEN_ELEMENT)]) > compute_score([det(30, S.VISIBLE_TEXT)])


def test_repeats_in_one_category_have_diminishing_returns() -> None:
    one = compute_score([det(20)])
    two = compute_score([det(20), det(20)])
    many = compute_score([det(20)] * 20)
    assert one < two < 2 * one
    assert many <= 2 * one + 1  # geometric series converges to twice the first


def test_spread_across_sources_earns_a_bonus() -> None:
    same_source = compute_score(
        [
            det(20, S.META_TAG, Category.PERSONA_OVERRIDE),
            det(20, S.META_TAG, Category.STEALTH_INSTRUCTION),
        ]
    )
    two_sources = compute_score(
        [
            det(20, S.META_TAG, Category.PERSONA_OVERRIDE),
            det(20, S.IMAGE_ALT, Category.STEALTH_INSTRUCTION),
        ]
    )
    assert two_sources == same_source + 10


def test_score_never_exceeds_100() -> None:
    every_category_everywhere = [det(50, source, category) for source in S for category in Category]
    assert compute_score(every_category_everywhere) == 100


def test_scoring_is_deterministic() -> None:
    detections = [det(25, S.HTML_COMMENT), det(15, S.META_TAG, Category.PERSONA_OVERRIDE)]
    assert len({compute_score(detections) for _ in range(50)}) == 1
    assert compute_score(detections) == compute_score(list(reversed(detections)))


def test_multi_vector_page_outscores_every_single_source_page() -> None:
    """Acceptance criterion: three sources score higher than any one."""
    from app.services.scanner.demo_pages import DEMO_PAGES, load_demo_content

    multi = scan_document(load_demo_content("multi_vector")).score
    for demo_id, page in DEMO_PAGES.items():
        if page.expected_findings <= 1:
            assert scan_document(load_demo_content(demo_id)).score < multi, page.filename
