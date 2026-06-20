"""
ShadowScan HTML Report Generator
Generates self-contained HTML reports with Jinja2 autoescape enabled.
All dynamic content is escaped to prevent XSS.
"""

import os
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.models import ScanResult
from app.config import settings


TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Jinja2 environment with autoescape enabled for security
_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def generate_html_report(scan: ScanResult) -> str:
    """
    Generate a self-contained HTML report for a completed scan.

    Args:
        scan: ScanResult with findings loaded

    Returns:
        Complete HTML string for the report
    """
    template = _env.get_template("scan_report.html")

    # Group findings by category
    findings_by_category = {}
    for finding in scan.findings:
        cat = finding.matched_category
        if cat not in findings_by_category:
            findings_by_category[cat] = []
        findings_by_category[cat].append(finding)

    # Group findings by source
    findings_by_source = {}
    for finding in scan.findings:
        src = finding.source_location
        if src not in findings_by_source:
            findings_by_source[src] = []
        findings_by_source[src].append(finding)

    target = scan.target_url or scan.target_filename or "Unknown target"
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    html = template.render(
        scan=scan,
        target=target,
        findings_by_category=findings_by_category,
        findings_by_source=findings_by_source,
        generated_at=generated_at,
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
    )

    return html
