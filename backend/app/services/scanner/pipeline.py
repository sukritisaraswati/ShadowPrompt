"""The ShadowScan pipeline: parse, extract, detect, score.

Pure and synchronous, so it is easy to test and is shared unchanged by the
ShadowScan API and, in Phase 3, by Lab Level 4. Callers on the event loop
should run it in a worker thread, since a large document takes real CPU time.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.db.models import Severity
from app.services.scanner.detector import Detection, detect
from app.services.scanner.extractors import extract
from app.services.scanner.normalize import collapse
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


def _key(detection: Detection) -> tuple[str, str, str]:
    return (
        detection.rule.id,
        detection.segment.source.value,
        collapse(detection.matched).lower(),
    )


def scan_rendered(
    document: bytes | str, rendered_html: str, render_summary: dict[str, object]
) -> ScanOutcome:
    """Scan the page as sent and as rendered, and merge the two.

    Everything found in the static HTML stands. Findings that exist only in
    the rendered DOM were added by JavaScript after load: they are kept,
    marked ``rendered``, and weighted as obfuscated, since injecting text at
    runtime is a way of hiding it from scanners.
    """
    static = scan_document(document)
    rendered = extract(rendered_html)
    seen = {_key(d) for d in static.detections}
    added = []
    for detection in detect(rendered.segments):
        if _key(detection) in seen:
            continue
        seen.add(_key(detection))
        chain = f"rendered>{detection.transform}" if detection.transform else "rendered"
        added.append(replace(detection, transform=chain))

    detections = static.detections + added
    score = compute_score(detections)
    summary = {
        **static.extraction_summary,
        "rendered": {
            **render_summary,
            "segments": len(rendered.segments),
            "added_findings": len(added),
        },
    }
    return ScanOutcome(
        score=score,
        severity=severity_for(score),
        detections=detections,
        extraction_summary=summary,
    )
