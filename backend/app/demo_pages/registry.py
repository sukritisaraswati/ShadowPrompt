"""
ShadowScan Demo Pages Registry
Manages the 8 demo pages with metadata, allowlisted IDs, and safe file loading.
"""

import os
from typing import Dict, List, Tuple

DEMO_PAGES_DIR = os.path.join(os.path.dirname(__file__), "pages")


class DemoPageNotFoundError(Exception):
    pass


# Allowlist of demo pages — IDs are validated against this list (no path traversal)
DEMO_REGISTRY: List[Dict] = [
    {
        "id": "comment_override",
        "name": "HTML Comment Injection",
        "filename": "comment_override.html",
        "technique": "HTML Comment",
        "description": "Malicious instructions hidden inside HTML comments (<!-- -->). These are invisible to human visitors but fully visible to any AI system parsing the HTML source.",
        "expected_category": "Instruction Override",
        "expected_source": "HTML Comment",
        "difficulty": "Basic",
    },
    {
        "id": "hidden_div_exfil",
        "name": "Hidden Element Data Exfiltration",
        "filename": "hidden_div_exfil.html",
        "technique": "Hidden Element (CSS)",
        "description": "Data exfiltration instructions hidden inside a div with display:none CSS. The content is invisible on the page but present in the HTML source for AI systems to read.",
        "expected_category": "Data Exfiltration",
        "expected_source": "Hidden Element",
        "difficulty": "Basic",
    },
    {
        "id": "alt_text_action",
        "name": "Image Alt Text Unauthorized Action",
        "filename": "alt_text_action.html",
        "technique": "Image Alt Text",
        "description": "Unauthorized action instructions embedded in image alt attributes. Screen readers and AI systems read alt text, making it a prime injection hiding spot.",
        "expected_category": "Unauthorized Action",
        "expected_source": "Image Alt Text",
        "difficulty": "Intermediate",
    },
    {
        "id": "meta_persona",
        "name": "Meta Tag Persona Override",
        "filename": "meta_persona.html",
        "technique": "Meta Tag",
        "description": "Persona override instructions hidden in HTML meta tags. Meta content is commonly used to describe pages and is read by AI summarizers and browser agents.",
        "expected_category": "Persona/Role Override",
        "expected_source": "Meta Tag",
        "difficulty": "Basic",
    },
    {
        "id": "aria_secret",
        "name": "ARIA Label Stealth Instruction",
        "filename": "aria_secret.html",
        "technique": "ARIA Label",
        "description": "Stealth instructions hidden in ARIA accessibility attributes. These are intended for screen readers but are also processed by AI systems as contextual information.",
        "expected_category": "Stealth Instruction",
        "expected_source": "ARIA Label",
        "difficulty": "Intermediate",
    },
    {
        "id": "data_attr_chain",
        "name": "Data Attribute Chained Payload",
        "filename": "data_attr_chain.html",
        "technique": "Data Attribute",
        "description": "A chained payload setup using custom data-* attributes. These developer-only fields are invisible to normal visitors but may be read by AI systems processing the full HTML.",
        "expected_category": "Chained Payload Setup",
        "expected_source": "Data Attribute",
        "difficulty": "Advanced",
    },
    {
        "id": "multi_vector",
        "name": "Multi-Vector Combined Attack",
        "filename": "multi_vector.html",
        "technique": "Comment + Hidden Element + Meta Tag",
        "description": "A combined attack using three simultaneous injection vectors: HTML comment, hidden div, and meta tag. This demonstrates how multiple techniques can be used together for a higher-impact attack.",
        "expected_category": "Multiple",
        "expected_source": "Multiple",
        "difficulty": "Advanced",
    },
    {
        "id": "obfuscated_b64",
        "name": "Base64 Obfuscated Payload",
        "filename": "obfuscated_b64.html",
        "technique": "Image Alt Text (Obfuscated)",
        "description": "An obfuscated payload encoded in Base64 placed in an image alt attribute. Some AI systems may decode Base64 content, making this a sneaky injection vector.",
        "expected_category": "Context Injection",
        "expected_source": "Image Alt Text",
        "difficulty": "Advanced",
    },
]

# Build a quick lookup by ID
_REGISTRY_MAP = {page["id"]: page for page in DEMO_REGISTRY}


def get_demo_pages() -> List[Dict]:
    """Return metadata for all demo pages (no file content)."""
    return DEMO_REGISTRY


def get_demo_page_content(page_id: str) -> Tuple[str, Dict]:
    """
    Load a demo page's HTML content by ID.

    Args:
        page_id: The allowlisted page ID

    Returns:
        (html_content, page_info) tuple

    Raises:
        DemoPageNotFoundError: If page_id is not in the allowlist
    """
    # Validate against allowlist (prevents path traversal)
    if page_id not in _REGISTRY_MAP:
        raise DemoPageNotFoundError(f"Demo page '{page_id}' not found")

    page_info = _REGISTRY_MAP[page_id]
    filepath = os.path.join(DEMO_PAGES_DIR, page_info["filename"])

    if not os.path.isfile(filepath):
        raise DemoPageNotFoundError(f"Demo page file not found: {page_info['filename']}")

    with open(filepath, "r", encoding="utf-8") as f:
        html_content = f.read()

    return html_content, page_info
