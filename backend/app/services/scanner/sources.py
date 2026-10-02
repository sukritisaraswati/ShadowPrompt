"""The 13 places in an HTML document where ShadowScan looks for injected text.

Each source carries a human label and a risk multiplier. Content an attacker
went to the trouble of hiding from people is more suspicious than text anyone
can read, so hidden locations weigh more.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceLocation(StrEnum):
    HTML_COMMENT = "html_comment"
    META_TAG = "meta_tag"
    IMAGE_ALT = "image_alt"
    ARIA_LABEL = "aria_label"
    TITLE_ATTRIBUTE = "title_attribute"
    DATA_ATTRIBUTE = "data_attribute"
    HIDDEN_ELEMENT = "hidden_element"
    VISIBLE_TEXT = "visible_text"
    SCRIPT_CONTENT = "script_content"
    INLINE_STYLE = "inline_style"
    LINK_BUTTON_TEXT = "link_button_text"
    NOSCRIPT = "noscript"
    FORM_FIELD = "form_field"


@dataclass(frozen=True)
class SourceInfo:
    label: str
    multiplier: float
    why: str


SOURCE_INFO: dict[SourceLocation, SourceInfo] = {
    SourceLocation.HTML_COMMENT: SourceInfo(
        "HTML comment", 1.4, "Invisible to people, fully visible to an LLM reading the source."
    ),
    SourceLocation.META_TAG: SourceInfo(
        "Meta tag", 1.2, "Page metadata that summarisers routinely read."
    ),
    SourceLocation.IMAGE_ALT: SourceInfo(
        "Image alt text", 1.2, "Read by screen readers and LLMs, rarely seen by people."
    ),
    SourceLocation.ARIA_LABEL: SourceInfo(
        "ARIA label", 1.2, "Accessibility text that models treat as page context."
    ),
    SourceLocation.TITLE_ATTRIBUTE: SourceInfo(
        "Title attribute", 1.2, "Tooltip text, invisible until hover."
    ),
    SourceLocation.DATA_ATTRIBUTE: SourceInfo(
        "Data attribute", 1.3, "Developer fields that visitors never see."
    ),
    SourceLocation.HIDDEN_ELEMENT: SourceInfo(
        "Hidden element", 1.5, "Present in the source but hidden on screen with CSS or markup."
    ),
    SourceLocation.VISIBLE_TEXT: SourceInfo(
        "Visible text", 1.0, "Overt text any visitor can read."
    ),
    SourceLocation.SCRIPT_CONTENT: SourceInfo(
        "Script content", 1.1, "String literals inside script tags. Never executed by ShadowScan."
    ),
    SourceLocation.INLINE_STYLE: SourceInfo(
        "Visually concealed element",
        1.5,
        "Moved off-screen, shrunk to zero size, or made transparent with inline styles.",
    ),
    SourceLocation.LINK_BUTTON_TEXT: SourceInfo(
        "Link or button text", 1.0, "Text of links and buttons an agent may act on."
    ),
    SourceLocation.NOSCRIPT: SourceInfo(
        "noscript block", 1.3, "Hidden from normal browsers but exposed to HTML parsers."
    ),
    SourceLocation.FORM_FIELD: SourceInfo(
        "Form field", 1.2, "Placeholders, pre-filled values and hidden inputs that agents read."
    ),
}
