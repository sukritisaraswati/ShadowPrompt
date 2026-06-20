"""
ShadowScan Risk Scoring Engine
Deterministic risk scoring based on configurable weights.
Score is always 0-100, severity maps to Clean/Low/Medium/High/Critical.
"""

from typing import List, Tuple
from app.scanner.detector import DetectionMatch
from app.config import SOURCE_WEIGHTS, CATEGORY_MULTIPLIERS, settings


def calculate_risk_score(matches: List[DetectionMatch]) -> Tuple[int, str, List[dict]]:
    """
    Calculate the overall risk score from detection matches.

    Returns:
        (score, severity, score_breakdown)
        - score: 0-100 integer
        - severity: "Clean", "Low", "Medium", "High", or "Critical"
        - score_breakdown: list of dicts showing each finding's score contribution
    """
    if not matches:
        return 0, "Clean", []

    score_breakdown = []
    raw_score = 0.0
    unique_sources = set()

    for match in matches:
        # Get base weight from source location
        source_weight = SOURCE_WEIGHTS.get(match.source_type, 10)

        # Get severity multiplier from category
        category_multiplier = CATEGORY_MULTIPLIERS.get(match.category, 1.0)

        # Calculate finding weight
        finding_weight = round(source_weight * category_multiplier, 1)
        raw_score += finding_weight

        unique_sources.add(match.source_type)

        score_breakdown.append({
            "category": match.category,
            "source_type": match.source_type,
            "matched_rule": match.matched_rule,
            "source_weight": source_weight,
            "category_multiplier": category_multiplier,
            "finding_weight": finding_weight,
        })

    # Bonus for multiple unique injection sources (after the first)
    additional_sources = max(0, len(unique_sources) - 1)
    source_bonus = additional_sources * settings.BONUS_PER_ADDITIONAL_SOURCE
    raw_score += source_bonus

    # Cap at 100, floor at 0
    final_score = max(0, min(100, round(raw_score)))

    # Map to severity
    severity = score_to_severity(final_score)

    return final_score, severity, score_breakdown


def score_to_severity(score: int) -> str:
    """Map a numeric score to a severity string."""
    if score <= settings.SEVERITY_CLEAN_MAX:
        return "Clean"
    elif score <= settings.SEVERITY_LOW_MAX:
        return "Low"
    elif score <= settings.SEVERITY_MEDIUM_MAX:
        return "Medium"
    elif score <= settings.SEVERITY_HIGH_MAX:
        return "High"
    else:
        return "Critical"
