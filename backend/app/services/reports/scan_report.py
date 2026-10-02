"""Self-contained HTML report for a ShadowScan result (blueprint 13.2).

Every value from the scanned page is attacker-controlled. Jinja2 runs with
autoescaping forced on, the report loads nothing external, and it carries its
own Content Security Policy that forbids scripts even if escaping were ever
bypassed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app import __version__
from app.db.models import ScanResult
from app.schemas.scan import ScanResultOut
from app.services.scan_service import result_out

TEMPLATE_DIR = Path(__file__).parent / "templates"

# No scripts, no external fetches, no forms, no framing. Inline styles only.
REPORT_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


@lru_cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _executive_summary(result: ScanResultOut) -> str:
    if not result.findings:
        return (
            "ShadowScan found no content matching its injection rules. The page appears safe "
            "for LLM processing, within the limitations listed at the end of this report."
        )
    sources = {f.source_label for f in result.findings}
    top = result.findings[0]  # findings are ordered by risk weight
    noun = "finding" if len(result.findings) == 1 else "findings"
    place = "location" if len(sources) == 1 else "locations"
    return (
        f"ShadowScan found {len(result.findings)} {noun} across {len(sources)} source {place}. "
        f"The highest-risk finding is {top.category_label.lower()} in {top.source_label.lower()}. "
        f"Overall risk is {result.severity.label.lower()}: {result.severity.meaning} "
        f"Recommended action: {result.severity.recommended_action}"
    )


def _remediation_checklist(result: ScanResultOut) -> list[str]:
    seen: dict[str, str] = {}
    for finding in result.findings:
        if finding.remediation and finding.category not in seen:
            seen[finding.category] = f"{finding.category_label}: {finding.remediation}"
    return list(seen.values())


def render_scan_report(scan: ScanResult) -> str:
    result = result_out(scan)
    target = result.target_url or result.target_filename or "Unknown target"
    return (
        _environment()
        .get_template("scan_report.html.j2")
        .render(
            result=result,
            target=target,
            csp=REPORT_CSP,
            version=__version__,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            scanned_at=result.created_at.strftime("%Y-%m-%d %H:%M UTC"),
            summary=_executive_summary(result),
            checklist=_remediation_checklist(result),
        )
    )
