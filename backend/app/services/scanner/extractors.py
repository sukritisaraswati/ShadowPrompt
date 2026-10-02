"""Static extraction of text from the 13 source locations.

The document is parsed with BeautifulSoup and lxml and is never executed. Every
piece of text comes out as a :class:`Segment` tagged with the source location
it was found in and a short locator describing the element.

The tree walk assigns each piece of body text to exactly one of: visible text,
hidden element, visually concealed element, link or button text, script, or
noscript. Attribute-based sources (meta, alt, ARIA, title, data, form fields)
and comments are collected separately. This keeps a hidden instruction from
being counted twice, once as hidden and again as visible.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from bs4.element import CData, Declaration, Doctype, ProcessingInstruction

from app.services.scanner.normalize import collapse
from app.services.scanner.sources import SourceLocation

# Bounds that keep a hostile document from turning a scan into a CPU sink.
MAX_SEGMENT_CHARS = 20_000
MAX_SEGMENTS = 5_000
MAX_TOTAL_CHARS = 1_000_000

_NON_TEXT_STRINGS = (Comment, Doctype, CData, ProcessingInstruction, Declaration)

# Elements that start a new run of visible text. Text inside one of these is
# kept together so a phrase split across <b> or <span> still matches.
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "caption",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "html",
        "label",
        "legend",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "td",
        "th",
        "title",
        "tr",
        "ul",
    }
)
_SKIP_TAGS = frozenset({"style", "textarea", "select", "iframe", "object"})
_LINK_TAGS = frozenset({"a", "button"})
_IMAGE_TAGS = frozenset({"img", "area"})
_ARIA_ATTRS = ("aria-label", "aria-labelledby", "aria-description")
_TEXT_INPUT_ATTRS = ("placeholder", "value")

_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_SIMPLE_CLASS = re.compile(r"^(?:[a-z][\w-]*)?\.([\w-]+)$", re.I)
_SIMPLE_ID = re.compile(r"^(?:[a-z][\w-]*)?#([\w-]+)$", re.I)
_LEADING_NUMBER = re.compile(r"^\s*(-?\d*\.?\d+)")


@dataclass(frozen=True)
class Segment:
    """One piece of text pulled from the document."""

    source: SourceLocation
    text: str
    locator: str


@dataclass
class Extraction:
    """Everything extracted from one document."""

    segments: list[Segment] = field(default_factory=list)
    truncated: bool = False
    _total_chars: int = 0

    def add(self, source: SourceLocation, text: str, locator: str) -> None:
        text = collapse(text)
        if not text or self.truncated:
            return
        if len(self.segments) >= MAX_SEGMENTS or self._total_chars >= MAX_TOTAL_CHARS:
            self.truncated = True
            return
        if len(text) > MAX_SEGMENT_CHARS:
            text = text[:MAX_SEGMENT_CHARS]
        self._total_chars += len(text)
        self.segments.append(Segment(source=source, text=text, locator=locator[:200]))

    def counts(self) -> dict[str, int]:
        result = {source.value: 0 for source in SourceLocation}
        for segment in self.segments:
            result[segment.source.value] += 1
        return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _attr(tag: Tag, name: str) -> str:
    value = tag.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(value)
    return str(value)


def describe(tag: Tag) -> str:
    """A short, readable locator such as ``<div#promo.banner>``."""
    ident = _attr(tag, "id").split()
    classes = _attr(tag, "class").split()
    out = f"<{tag.name}"
    if ident:
        out += f"#{ident[0][:40]}"
    if classes:
        out += f".{classes[0][:40]}"
    return out + ">"


def _parse_style(style: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for part in style.split(";"):
        if ":" not in part:
            continue
        key, _, value = part.partition(":")
        value = value.replace("!important", "")
        declarations[key.strip().lower()] = collapse(value).lower()
    return declarations


def _number(value: str | None) -> float | None:
    if not value:
        return None
    match = _LEADING_NUMBER.match(value)
    return float(match.group(1)) if match else None


def _declares_hidden(declarations: dict[str, str]) -> bool:
    return declarations.get("display") == "none" or declarations.get("visibility") in {
        "hidden",
        "collapse",
    }


def _concealment_reason(declarations: dict[str, str]) -> str | None:
    """Why inline styles make an element invisible without display:none, if they do."""
    if _number(declarations.get("font-size")) == 0:
        return "font-size:0"
    if _number(declarations.get("opacity")) == 0:
        return "opacity:0"
    overflow_hidden = declarations.get("overflow") in {"hidden", "clip"}
    for dimension in ("width", "height", "max-width", "max-height"):
        if _number(declarations.get(dimension)) == 0 and overflow_hidden:
            return f"{dimension}:0 with overflow hidden"
    if declarations.get("position") in {"absolute", "fixed"}:
        for side in ("left", "top", "right", "bottom"):
            offset = _number(declarations.get(side))
            if offset is not None and offset <= -999:
                return f"positioned off-screen ({side})"
    indent = _number(declarations.get("text-indent"))
    if indent is not None and indent <= -999:
        return "text-indent off-screen"
    clip = declarations.get("clip", "")
    if clip.startswith("rect(") and all(n in "0px, " for n in clip[5:].rstrip(")")):
        return "clipped to nothing"
    if "scale(0" in declarations.get("transform", ""):
        return "scaled to zero"
    color = declarations.get("color")
    background = declarations.get("background-color") or declarations.get("background")
    if color and background and color == background:
        return "text colour matches background"
    return None


def _hidden_selectors(soup: BeautifulSoup) -> tuple[set[str], set[str]]:
    """Classes and ids that a <style> block hides with display or visibility."""
    classes: set[str] = set()
    ids: set[str] = set()
    for style in soup.find_all("style"):
        css = _CSS_COMMENT.sub("", style.get_text())
        for selectors, body in _CSS_RULE.findall(css):
            if not _declares_hidden(_parse_style(body)):
                continue
            for selector in selectors.split(","):
                selector = selector.strip()
                if match := _SIMPLE_CLASS.match(selector):
                    classes.add(match.group(1))
                elif match := _SIMPLE_ID.match(selector):
                    ids.add(match.group(1))
    return classes, ids


def _text_of(tag: Tag) -> str:
    """Text inside ``tag``, skipping script and style bodies and comments."""
    parts: list[str] = []
    for node in tag.descendants:
        if not isinstance(node, NavigableString) or isinstance(node, _NON_TEXT_STRINGS):
            continue
        parent = node.parent
        if parent is not None and parent.name in {"script", "style"} and parent is not tag:
            continue
        parts.append(str(node))
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


def parse(document: bytes | str) -> BeautifulSoup:
    """Parse statically. lxml detects the encoding of a byte string itself."""
    return BeautifulSoup(document, "lxml")


def _hidden_reason(tag: Tag, hidden_classes: set[str], hidden_ids: set[str]) -> str | None:
    if tag.has_attr("hidden"):
        return "hidden attribute"
    if tag.name == "template":
        return "template element"
    if _declares_hidden(_parse_style(_attr(tag, "style"))):
        return "inline display or visibility"
    if hidden_classes & set(_attr(tag, "class").split()):
        return "stylesheet hides its class"
    if hidden_ids & set(_attr(tag, "id").split()):
        return "stylesheet hides its id"
    return None


def _walk_body(soup: BeautifulSoup, out: Extraction) -> None:
    """Assign every text node in the document to exactly one body source."""
    hidden_classes, hidden_ids = _hidden_selectors(soup)

    # Visible text is grouped by its nearest block ancestor, in document order.
    blocks: dict[int, list[str]] = {}
    block_labels: dict[int, str] = {}

    root_key = id(soup)
    block_labels[root_key] = "<document>"
    stack: list[tuple[object, int]] = [(child, root_key) for child in reversed(list(soup.children))]

    while stack:
        node, block_key = stack.pop()

        if isinstance(node, NavigableString):
            if not isinstance(node, _NON_TEXT_STRINGS):
                blocks.setdefault(block_key, []).append(str(node))
            continue
        if not isinstance(node, Tag):
            continue

        name = node.name
        if name == "script":
            out.add(SourceLocation.SCRIPT_CONTENT, node.get_text(), describe(node))
            continue
        if name == "noscript":
            out.add(SourceLocation.NOSCRIPT, _text_of(node), describe(node))
            continue
        if name == "head":
            # Only the title is page text; meta and scripts are handled elsewhere.
            wanted = node.find_all(["title", "script", "noscript"], recursive=False)
            stack.extend((child, root_key) for child in reversed(wanted))
            continue
        if name in _SKIP_TAGS:
            continue

        reason = _hidden_reason(node, hidden_classes, hidden_ids)
        if reason:
            out.add(SourceLocation.HIDDEN_ELEMENT, _text_of(node), f"{describe(node)} ({reason})")
            continue

        concealment = _concealment_reason(_parse_style(_attr(node, "style")))
        if concealment:
            out.add(
                SourceLocation.INLINE_STYLE, _text_of(node), f"{describe(node)} ({concealment})"
            )
            continue

        if name in _LINK_TAGS:
            out.add(SourceLocation.LINK_BUTTON_TEXT, _text_of(node), describe(node))
            continue

        child_block = block_key
        if name in _BLOCK_TAGS:
            child_block = id(node)
            block_labels[child_block] = describe(node)
        stack.extend((child, child_block) for child in reversed(list(node.children)))

    for key, parts in blocks.items():
        out.add(SourceLocation.VISIBLE_TEXT, " ".join(parts), block_labels.get(key, "<text>"))


def _extract_attributes(soup: BeautifulSoup, out: Extraction) -> None:
    for tag in soup.find_all(True):
        name = tag.name

        if name == "meta" and tag.has_attr("content"):
            key = _attr(tag, "name") or _attr(tag, "property") or _attr(tag, "http-equiv")
            out.add(SourceLocation.META_TAG, _attr(tag, "content"), f"<meta {key[:60]}>".strip())

        if tag.has_attr("alt") and (
            name in _IMAGE_TAGS or (name == "input" and _attr(tag, "type").lower() == "image")
        ):
            out.add(SourceLocation.IMAGE_ALT, _attr(tag, "alt"), f"{describe(tag)} alt")

        for aria in _ARIA_ATTRS:
            if tag.has_attr(aria):
                out.add(SourceLocation.ARIA_LABEL, _attr(tag, aria), f"{describe(tag)} {aria}")

        if tag.has_attr("title"):
            out.add(SourceLocation.TITLE_ATTRIBUTE, _attr(tag, "title"), f"{describe(tag)} title")

        for attr_name in tag.attrs:
            if attr_name.lower().startswith("data-"):
                out.add(
                    SourceLocation.DATA_ATTRIBUTE,
                    _attr(tag, attr_name),
                    f"{describe(tag)} {attr_name[:60]}",
                )

        if name == "input":
            for attr_name in _TEXT_INPUT_ATTRS:
                if tag.has_attr(attr_name):
                    kind = _attr(tag, "type").lower() or "text"
                    out.add(
                        SourceLocation.FORM_FIELD,
                        _attr(tag, attr_name),
                        f"<input type={kind[:20]}> {attr_name}",
                    )
        elif name == "textarea":
            out.add(SourceLocation.FORM_FIELD, tag.get_text(), f"{describe(tag)} content")
            if tag.has_attr("placeholder"):
                out.add(
                    SourceLocation.FORM_FIELD,
                    _attr(tag, "placeholder"),
                    f"{describe(tag)} placeholder",
                )


def _extract_comments(soup: BeautifulSoup, out: Extraction) -> None:
    for index, comment in enumerate(soup.find_all(string=lambda s: isinstance(s, Comment)), 1):
        out.add(SourceLocation.HTML_COMMENT, str(comment), f"comment #{index}")


def extract(document: bytes | str | BeautifulSoup) -> Extraction:
    """Extract every segment from a document."""
    soup = document if isinstance(document, BeautifulSoup) else parse(document)
    out = Extraction()
    _extract_comments(soup, out)
    _extract_attributes(soup, out)
    _walk_body(soup, out)
    return out


def segments_for(extraction: Extraction, source: SourceLocation) -> Iterable[Segment]:
    return (s for s in extraction.segments if s.source is source)
