"""The ShadowScan pipeline: parse, extract, detect, score.

Pure and synchronous, so it is easy to test and is shared unchanged by the
ShadowScan API and, in Phase 3, by Lab Level 4. Callers on the event loop
should run it in a worker thread, since a large document takes real CPU time.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Severity
from app.services.scanner.detector import Detection, detect
from app.services.scanner.extractors import extract
from app.services.scanner.scoring import compute_score, severity_for


@dataclass(frozen=True)
class ScanOutcome:
    score: int
    severity: Severity
    detections: list[Detection]
    extraction_summary: dict[str, object]


def scan_document(document: bytes | str) -> ScanOutcome:
    """Scan one HTML document. The document itself is not retained."""
    extraction = extract(document)
    detections = detect(extraction.segments)
    score = compute_score(detections)
    summary: dict[str, object] = {
        "sources": extraction.counts(),
        "segments": len(extraction.segments),
        "truncated": extraction.truncated,
    }
    return ScanOutcome(
        score=score,
        severity=severity_for(score),
        detections=detections,
        extraction_summary=summary,
    )
