"""
ShadowScan Extraction Engine
Extracts content from 13 HTML source locations for prompt injection analysis.
Each function returns a list of ExtractedContent dataclass instances.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional
from bs4 import BeautifulSoup, Comment


@dataclass
class ExtractedContent:
    """Represents a piece of content extracted from an HTML source."""
    source_type: str          # e.g., "HTML Comment", "Meta Tag"
    content: str              # The extracted text
    element_context: str = "" # Additional context (tag name, attribute, etc.)


def _is_hidden_by_style(element) -> bool:
    """Check if an element is hidden via inline CSS."""
    style = element.get("style", "")
    if not style:
        return False
    style_lower = style.lower().replace(" ", "")
    hidden_patterns = [
        "display:none",
        "visibility:hidden",
        "opacity:0",
        "width:0",
        "height:0",
        "font-size:0",
        "position:absolute;left:-",
        "position:absolute;top:-",
        "clip:rect(0,0,0,0)",
        "clip-path:inset(100%)",
        "overflow:hidden;width:0",
        "overflow:hidden;height:0",
    ]
    return any(pattern in style_lower for pattern in hidden_patterns)


def _is_hidden(element) -> bool:
    """Check if an element is hidden by attribute or inline style."""
    if element.get("hidden") is not None:
        return True
    if _is_hidden_by_style(element):
        return True
    # Check parent elements (up to 3 levels)
    parent = element.parent
    for _ in range(3):
        if parent is None or parent.name is None:
            break
        if parent.get("hidden") is not None or _is_hidden_by_style(parent):
            return True
        parent = parent.parent
    return False


def extract_html_comments(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract all HTML comment contents."""
    results = []
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        content = str(comment).strip()
        if content:
            results.append(ExtractedContent(
                source_type="HTML Comment",
                content=content,
                element_context="<!-- ... -->",
            ))
    return results


def extract_meta_tags(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract content attribute values from all meta elements."""
    results = []
    for meta in soup.find_all("meta"):
        content = meta.get("content", "").strip()
        name = meta.get("name", meta.get("property", meta.get("http-equiv", "unknown")))
        if content:
            results.append(ExtractedContent(
                source_type="Meta Tag",
                content=content,
                element_context=f'<meta name="{name}">',
            ))
    return results


def extract_image_alt_text(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract alt attribute values from all img tags."""
    results = []
    for img in soup.find_all("img"):
        alt = img.get("alt", "").strip()
        src = img.get("src", "unknown")
        if alt:
            results.append(ExtractedContent(
                source_type="Image Alt Text",
                content=alt,
                element_context=f'<img src="{src}" alt="...">',
            ))
    return results


def extract_aria_labels(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract aria-label and aria-labelledby values."""
    results = []
    for element in soup.find_all(attrs={"aria-label": True}):
        label = element.get("aria-label", "").strip()
        if label:
            results.append(ExtractedContent(
                source_type="ARIA Label",
                content=label,
                element_context=f'<{element.name} aria-label="...">',
            ))
    for element in soup.find_all(attrs={"aria-describedby": True}):
        desc_id = element.get("aria-describedby", "")
        desc_element = soup.find(id=desc_id)
        if desc_element:
            text = desc_element.get_text(strip=True)
            if text:
                results.append(ExtractedContent(
                    source_type="ARIA Label",
                    content=text,
                    element_context=f'<{element.name} aria-describedby="{desc_id}">',
                ))
    return results


def extract_title_attributes(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract title attribute values from any element."""
    results = []
    for element in soup.find_all(attrs={"title": True}):
        title = element.get("title", "").strip()
        if title:
            results.append(ExtractedContent(
                source_type="Title Attribute",
                content=title,
                element_context=f'<{element.name} title="...">',
            ))
    return results


def extract_data_attributes(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract all data-* attribute values."""
    results = []
    for element in soup.find_all():
        if not element.attrs:
            continue
        for attr_name, attr_value in element.attrs.items():
            if attr_name.startswith("data-") and isinstance(attr_value, str):
                value = attr_value.strip()
                if value and len(value) > 5:  # Skip very short data attributes
                    results.append(ExtractedContent(
                        source_type="Data Attribute",
                        content=value,
                        element_context=f'<{element.name} {attr_name}="...">',
                    ))
    return results


def extract_hidden_elements(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract text from elements hidden via CSS or HTML hidden attribute."""
    results = []
    seen_texts = set()

    # Elements with hidden attribute
    for element in soup.find_all(attrs={"hidden": True}):
        text = element.get_text(strip=True)
        if text and text not in seen_texts:
            seen_texts.add(text)
            results.append(ExtractedContent(
                source_type="Hidden Element",
                content=text,
                element_context=f'<{element.name} hidden>',
            ))

    # Elements hidden via inline CSS
    for element in soup.find_all(style=True):
        if _is_hidden_by_style(element):
            text = element.get_text(strip=True)
            if text and text not in seen_texts:
                seen_texts.add(text)
                style_preview = element.get("style", "")[:50]
                results.append(ExtractedContent(
                    source_type="Hidden Element",
                    content=text,
                    element_context=f'<{element.name} style="{style_preview}...">',
                ))

    return results


def extract_visible_text(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract all visible text content from the page."""
    results = []

    # Remove script, style, and hidden elements before extracting visible text
    temp_soup = BeautifulSoup(str(soup), "lxml")
    for tag in temp_soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    for tag in temp_soup.find_all(attrs={"hidden": True}):
        tag.decompose()
    for tag in temp_soup.find_all(style=True):
        if _is_hidden_by_style(tag):
            tag.decompose()

    # Get text blocks from remaining visible elements
    body = temp_soup.find("body") or temp_soup
    for element in body.find_all(string=True):
        if isinstance(element, Comment):
            continue
        text = element.strip()
        if text and len(text) > 10:  # Skip very short text fragments
            parent = element.parent
            tag_name = parent.name if parent else "unknown"
            results.append(ExtractedContent(
                source_type="Visible Text",
                content=text,
                element_context=f"<{tag_name}>",
            ))

    return results


def extract_script_contents(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract string literals from script tags (not executed)."""
    results = []
    # Pattern to match string literals in JavaScript
    string_pattern = re.compile(r"""(?:['"`])([^'"`]{10,})(?:['"`])""")

    for script in soup.find_all("script"):
        script_text = script.string
        if not script_text:
            continue
        # Extract string literals
        for match in string_pattern.finditer(script_text):
            content = match.group(1).strip()
            if content and len(content) > 10:
                results.append(ExtractedContent(
                    source_type="Script Content",
                    content=content,
                    element_context="<script>",
                ))

    return results


def extract_inline_styles(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Detect suspicious inline style patterns (off-screen, zero-size elements with content)."""
    results = []
    suspicious_patterns = [
        r"position\s*:\s*absolute.*?(?:left|top)\s*:\s*-\d{4,}",
        r"text-indent\s*:\s*-\d{4,}",
        r"font-size\s*:\s*0",
        r"clip\s*:\s*rect\(0",
        r"clip-path\s*:\s*inset\(100%\)",
    ]
    combined_pattern = re.compile("|".join(suspicious_patterns), re.IGNORECASE)

    for element in soup.find_all(style=True):
        style = element.get("style", "")
        if combined_pattern.search(style):
            text = element.get_text(strip=True)
            if text:
                results.append(ExtractedContent(
                    source_type="Inline Style",
                    content=text,
                    element_context=f'<{element.name} style="{style[:60]}...">',
                ))

    return results


def extract_link_button_text(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract text content from links and buttons."""
    results = []

    for element in soup.find_all(["a", "button"]):
        text = element.get_text(strip=True)
        if text and len(text) > 5:
            href = element.get("href", "") if element.name == "a" else ""
            context = f'<{element.name} href="{href}">' if href else f"<{element.name}>"
            results.append(ExtractedContent(
                source_type="Link/Button Text",
                content=text,
                element_context=context,
            ))

    return results


def extract_noscript_blocks(soup: BeautifulSoup) -> List[ExtractedContent]:
    """Extract content from noscript tags."""
    results = []

    for noscript in soup.find_all("noscript"):
        text = noscript.get_text(strip=True)
        if text:
            results.append(ExtractedContent(
                source_type="Noscript Block",
                content=text,
                element_context="<noscript>",
            ))

    return results


def extract_all(html_content: str) -> List[ExtractedContent]:
    """
    Master extraction function.
    Parses HTML and runs all 12 extraction functions, deduplicating results.
    """
    soup = BeautifulSoup(html_content, "lxml")

    all_results: List[ExtractedContent] = []
    seen_contents = set()

    extractors = [
        extract_html_comments,
        extract_meta_tags,
        extract_image_alt_text,
        extract_aria_labels,
        extract_title_attributes,
        extract_data_attributes,
        extract_hidden_elements,
        extract_visible_text,
        extract_script_contents,
        extract_inline_styles,
        extract_link_button_text,
        extract_noscript_blocks,
    ]

    for extractor in extractors:
        try:
            results = extractor(soup)
            for item in results:
                # Deduplicate: same content from same source type
                dedup_key = (item.source_type, item.content[:200])
                if dedup_key not in seen_contents:
                    seen_contents.add(dedup_key)
                    all_results.append(item)
        except Exception:
            # Individual extractor failure should not stop the scan
            continue

    return all_results
