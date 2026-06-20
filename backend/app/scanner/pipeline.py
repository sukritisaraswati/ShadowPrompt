"""
ShadowScan Pipeline
Orchestrates the full scan flow: parse HTML → extract → detect → score → build result.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from app.scanner.extractor import extract_all, ExtractedContent
from app.scanner.detector import detect_patterns, DetectionMatch
from app.scanner.scorer import calculate_risk_score
from app.scanner.fetcher import fetch_url, FetchError


@dataclass
class ScanFinding:
    """A single finding ready for storage and API response."""
    source_location: str
    matched_rule: str
    matched_category: str
    evidence_text: str
    risk_weight: float
    impact: str
    remediation: str
    element_context: str = ""


@dataclass
class ScanOutput:
    """Complete result of a scan operation."""
    score: int
    severity: str
    findings: List[ScanFinding]
    finding_count: int
    score_breakdown: List[dict]
    target_url: Optional[str] = None
    target_filename: Optional[str] = None
    scan_type: str = "file"
    error: Optional[str] = None
    error_code: Optional[str] = None


def scan_html(html_content: str, scan_type: str = "file",
              target_url: str = None, target_filename: str = None) -> ScanOutput:
    """
    Run the full scan pipeline on HTML content.

    Args:
        html_content: Raw HTML string to analyze
        scan_type: "url", "file", or "demo"
        target_url: The URL that was scanned (if URL scan)
        target_filename: The filename that was uploaded (if file scan)

    Returns:
        ScanOutput with score, severity, findings, and breakdown
    """
    # Step 1: Extract content from all 13 sources
    extracted = extract_all(html_content)

    # Step 2: Detect suspicious patterns across 7 categories
    matches = detect_patterns(extracted)

    # Step 3: Calculate risk score
    score, severity, breakdown = calculate_risk_score(matches)

    # Step 4: Build findings list
    findings = []
    # Map each match to its corresponding score contribution
    breakdown_map = {}
    for item in breakdown:
        key = (item["category"], item["source_type"], item["matched_rule"])
        breakdown_map[key] = item["finding_weight"]

    for match in matches:
        key = (match.category, match.source_type, match.matched_rule)
        weight = breakdown_map.get(key, 0)

        findings.append(ScanFinding(
            source_location=match.source_type,
            matched_rule=match.matched_rule,
            matched_category=match.category,
            evidence_text=match.evidence[:2000],  # Cap evidence length
            risk_weight=weight,
            impact=match.impact,
            remediation=match.remediation,
            element_context=match.element_context,
        ))

    return ScanOutput(
        score=score,
        severity=severity,
        findings=findings,
        finding_count=len(findings),
        score_breakdown=breakdown,
        target_url=target_url,
        target_filename=target_filename,
        scan_type=scan_type,
    )


async def scan_url(url: str) -> ScanOutput:
    """
    Fetch a URL and run the full scan pipeline.

    Args:
        url: The URL to fetch and scan

    Returns:
        ScanOutput with results or error information
    """
    try:
        html_content, final_url = await fetch_url(url)
    except FetchError as e:
        return ScanOutput(
            score=0,
            severity="Clean",
            findings=[],
            finding_count=0,
            score_breakdown=[],
            target_url=url,
            scan_type="url",
            error=e.message,
            error_code=e.error_code,
        )

    return scan_html(
        html_content=html_content,
        scan_type="url",
        target_url=final_url,
    )
