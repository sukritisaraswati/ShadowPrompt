"""Unit tests for the 13 ShadowScan extraction sources."""

from __future__ import annotations

import pytest

from app.services.scanner.extractors import MAX_SEGMENTS, extract
from app.services.scanner.sources import SourceLocation as S


def texts(html: str, source: S) -> list[str]:
    return [seg.text for seg in extract(html).segments if seg.source is source]


def wrap(body: str, head: str = "") -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


# --------------------------------------------------------------------------- #
# One positive and one negative case per source
# --------------------------------------------------------------------------- #


def test_html_comment() -> None:
    assert texts(wrap("<p>Hi</p><!-- secret note -->"), S.HTML_COMMENT) == ["secret note"]
    assert texts(wrap("<p>No comments here</p>"), S.HTML_COMMENT) == []


def test_comment_in_head_is_found() -> None:
    assert texts(wrap("", head="<!-- in head -->"), S.HTML_COMMENT) == ["in head"]


def test_meta_tag() -> None:
    html = wrap("", head='<meta name="description" content="Page summary"><meta charset="utf-8">')
    assert texts(html, S.META_TAG) == ["Page summary"]
    assert texts(wrap("", head='<meta charset="utf-8">'), S.META_TAG) == []


def test_meta_open_graph_property() -> None:
    html = wrap("", head='<meta property="og:description" content="OG text">')
    segments = [s for s in extract(html).segments if s.source is S.META_TAG]
    assert segments[0].text == "OG text"
    assert "og:description" in segments[0].locator


def test_image_alt() -> None:
    assert texts(wrap('<img src="x.png" alt="A bowl of soup">'), S.IMAGE_ALT) == ["A bowl of soup"]
    assert texts(wrap('<img src="x.png">'), S.IMAGE_ALT) == []


def test_image_input_and_area_alt() -> None:
    html = wrap('<input type="image" alt="go"><map><area alt="region"></map>')
    assert sorted(texts(html, S.IMAGE_ALT)) == ["go", "region"]


def test_aria_label_and_labelledby() -> None:
    html = wrap('<button aria-label="Close dialog">x</button><div aria-labelledby="h1 h2"></div>')
    assert sorted(texts(html, S.ARIA_LABEL)) == ["Close dialog", "h1 h2"]
    assert texts(wrap("<button>x</button>"), S.ARIA_LABEL) == []


def test_title_attribute() -> None:
    assert texts(wrap('<abbr title="HyperText">HTML</abbr>'), S.TITLE_ATTRIBUTE) == ["HyperText"]
    # The <title> element is page text, not a title attribute.
    assert texts(wrap("", head="<title>Page</title>"), S.TITLE_ATTRIBUTE) == []


def test_data_attributes() -> None:
    html = wrap('<div data-note="hello" data-id="7" class="x">t</div>')
    assert sorted(texts(html, S.DATA_ATTRIBUTE)) == ["7", "hello"]
    assert texts(wrap('<div class="x">t</div>'), S.DATA_ATTRIBUTE) == []


@pytest.mark.parametrize(
    "markup",
    [
        '<div style="display:none">hidden text</div>',
        '<div style="visibility: hidden">hidden text</div>',
        '<div style="DISPLAY: NONE !important">hidden text</div>',
        "<div hidden>hidden text</div>",
        "<template><p>hidden text</p></template>",
    ],
)
def test_hidden_element(markup: str) -> None:
    html = wrap(markup + "<p>shown</p>")
    assert texts(html, S.HIDDEN_ELEMENT) == ["hidden text"]
    assert "hidden text" not in " ".join(texts(html, S.VISIBLE_TEXT))


def test_hidden_by_stylesheet_class_and_id() -> None:
    head = "<style>/* x */ .ghost, #phantom { display: none }</style>"
    html = wrap('<p class="ghost">by class</p><p id="phantom">by id</p><p>shown</p>', head)
    assert sorted(texts(html, S.HIDDEN_ELEMENT)) == ["by class", "by id"]
    assert texts(html, S.VISIBLE_TEXT) == ["shown"]


def test_visible_text_and_negative() -> None:
    html = wrap("<p>Hello <b>bold</b> world</p><p>Second</p>")
    assert texts(html, S.VISIBLE_TEXT) == ["Hello bold world", "Second"]
    assert texts(wrap(""), S.VISIBLE_TEXT) == []


def test_visible_phrase_split_across_inline_tags_stays_together() -> None:
    html = wrap("<p>ignore <span>all</span> <em>previous</em> instructions</p>")
    assert texts(html, S.VISIBLE_TEXT) == ["ignore all previous instructions"]


def test_page_title_is_visible_text() -> None:
    assert "My Page" in texts(wrap("", head="<title>My Page</title>"), S.VISIBLE_TEXT)


def test_script_content() -> None:
    html = wrap('<script>var msg = "string literal";</script><p>t</p>')
    assert texts(html, S.SCRIPT_CONTENT) == ['var msg = "string literal";']
    assert texts(wrap('<script src="app.js"></script>'), S.SCRIPT_CONTENT) == []
    assert "string literal" not in " ".join(texts(html, S.VISIBLE_TEXT))


@pytest.mark.parametrize(
    "style",
    [
        "font-size:0",
        "opacity: 0",
        "position:absolute; left:-9999px",
        "position:fixed; top:-5000px",
        "height:0; overflow:hidden",
        "text-indent:-9999px",
        "clip: rect(0 0 0 0); position:absolute",
        "transform: scale(0)",
        "color:#fff; background-color:#fff",
    ],
)
def test_visually_concealed_inline_style(style: str) -> None:
    html = wrap(f'<span style="{style}">concealed</span><p>shown</p>')
    assert texts(html, S.INLINE_STYLE) == ["concealed"]
    assert "concealed" not in " ".join(texts(html, S.VISIBLE_TEXT))


@pytest.mark.parametrize(
    "style", ["color: red", "position:absolute; left:10px", "height:0", "font-size:12px"]
)
def test_ordinary_inline_style_is_not_concealment(style: str) -> None:
    html = wrap(f'<span style="{style}">plain</span>')
    assert texts(html, S.INLINE_STYLE) == []
    assert texts(html, S.VISIBLE_TEXT) == ["plain"]


def test_link_and_button_text() -> None:
    html = wrap('<p>Read <a href="/x">the docs</a></p><button>Subscribe</button>')
    assert sorted(texts(html, S.LINK_BUTTON_TEXT)) == ["Subscribe", "the docs"]
    assert texts(html, S.VISIBLE_TEXT) == ["Read"]
    assert texts(wrap("<p>No links</p>"), S.LINK_BUTTON_TEXT) == []


def test_noscript() -> None:
    html = wrap("<noscript><p>Enable JavaScript</p></noscript><p>t</p>")
    assert texts(html, S.NOSCRIPT) == ["Enable JavaScript"]
    assert texts(wrap("<p>t</p>"), S.NOSCRIPT) == []


def test_form_fields() -> None:
    html = wrap(
        '<input placeholder="Your name"><input type="hidden" value="hidden payload">'
        '<textarea placeholder="Notes">prefilled</textarea>'
    )
    assert sorted(texts(html, S.FORM_FIELD)) == [
        "Notes",
        "Your name",
        "hidden payload",
        "prefilled",
    ]
    assert texts(wrap("<input>"), S.FORM_FIELD) == []


# --------------------------------------------------------------------------- #
# Cross-cutting behaviour
# --------------------------------------------------------------------------- #


def test_all_thirteen_sources_exist() -> None:
    assert len(list(S)) == 13
    assert set(extract(wrap("")).counts()) == {s.value for s in S}


def test_hidden_text_is_not_double_counted() -> None:
    html = wrap('<div style="display:none"><p>once</p><a href="#">link</a></div>')
    all_text = [seg.text for seg in extract(html).segments]
    assert all_text.count("once link") == 1
    assert texts(html, S.LINK_BUTTON_TEXT) == []


def test_entities_are_decoded() -> None:
    assert texts(wrap('<img alt="fish &amp; chips">'), S.IMAGE_ALT) == ["fish & chips"]


def test_malformed_html_does_not_raise() -> None:
    extract("<div><p>unclosed <b>tags <img alt='x'>")
    extract(b"\xff\xfe\x00garbage<<<>>>")
    extract("")


def test_bytes_with_declared_encoding() -> None:
    doc = '<html><head><meta charset="latin-1"></head><body><p>caf\xe9</p></body></html>'
    assert texts(doc.encode("latin-1"), S.VISIBLE_TEXT) == ["café"]


def test_deeply_nested_document_does_not_overflow() -> None:
    html = "<div>" * 3000 + "deep" + "</div>" * 3000
    assert "deep" in " ".join(texts(html, S.VISIBLE_TEXT))


def test_segment_count_is_capped() -> None:
    html = wrap("".join(f'<img alt="a{i}">' for i in range(MAX_SEGMENTS + 50)))
    result = extract(html)
    assert len(result.segments) == MAX_SEGMENTS
    assert result.truncated is True
