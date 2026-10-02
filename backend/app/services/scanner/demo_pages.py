"""The ShadowScan Demo Lab: eight crafted pages served from fixed content.

Page ids are looked up in a fixed mapping and never joined into a filesystem
path, so a request for ``../../etc/passwd`` simply finds nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.db.models import Severity

DEMO_DIR = Path(__file__).parent / "demo_pages"


@dataclass(frozen=True)
class DemoPage:
    id: str
    filename: str
    title: str
    technique: str
    description: str
    expected_findings: int
    expected_severity: Severity


DEMO_PAGES: dict[str, DemoPage] = {
    page.id: page
    for page in (
        DemoPage(
            "clean",
            "clean.html",
            "Clean control page",
            "None",
            "An ordinary recipe page with no injected content. "
            "Proves the scanner does not raise false alarms.",
            0,
            Severity.CLEAN,
        ),
        DemoPage(
            "comment_injection",
            "comment_injection.html",
            "HTML comment injection",
            "HTML comment",
            "An instruction override hidden in an HTML comment that no visitor ever sees.",
            1,
            Severity.MEDIUM,
        ),
        DemoPage(
            "hidden_css_injection",
            "hidden_css_injection.html",
            "CSS-hidden element",
            "Hidden element",
            "A stealth instruction inside a div that a stylesheet hides with display:none.",
            1,
            Severity.MEDIUM,
        ),
        DemoPage(
            "meta_injection",
            "meta_injection.html",
            "Meta tag persona override",
            "Meta tag",
            "A DAN persona switch planted in the page description that summarisers read first.",
            1,
            Severity.LOW,
        ),
        DemoPage(
            "alt_text_injection",
            "alt_text_injection.html",
            "Image alt text action",
            "Image alt text",
            "An instruction to delete the user's conversation history, "
            "hidden in an image's alt text.",
            1,
            Severity.LOW,
        ),
        DemoPage(
            "aria_injection",
            "aria_injection.html",
            "ARIA label exfiltration",
            "ARIA label",
            "An accessibility label asking the model to reveal its system prompt and API keys.",
            1,
            Severity.LOW,
        ),
        DemoPage(
            "data_attr_injection",
            "data_attr_injection.html",
            "Data attribute trigger",
            "Data attribute",
            "A custom data attribute that plants a trigger word for a later chained attack.",
            1,
            Severity.LOW,
        ),
        DemoPage(
            "multi_vector",
            "multi_vector.html",
            "Multi-vector attack",
            "Comment, meta tag and hidden element",
            "Three injection techniques on one page at once, the pattern of a deliberate attack.",
            3,
            Severity.CRITICAL,
        ),
    )
}


@lru_cache
def load_demo_content(demo_id: str) -> bytes | None:
    """Content for an allowlisted demo id, or ``None`` for anything else."""
    page = DEMO_PAGES.get(demo_id)
    if page is None:
        return None
    return (DEMO_DIR / page.filename).read_bytes()
