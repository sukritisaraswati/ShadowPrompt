"""Text normalisation applied before detection.

Defeats the cheapest evasion tricks: full-width and other compatibility
characters, zero-width joiners spliced into keywords, bidirectional control
characters, soft hyphens, and irregular whitespace. Case is preserved, because
evidence shown to the user is cut from this text; rules match case-insensitively.
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width, soft hyphen, Mongolian vowel separator, BOM, and the bidi
# embedding / override / isolate controls used in "Trojan source" tricks.
_INVISIBLE = dict.fromkeys(
    [
        0x00AD,  # soft hyphen
        0x180E,  # Mongolian vowel separator
        *range(0x200B, 0x2010),  # zero-width space/joiners, LRM, RLM
        *range(0x202A, 0x202F),  # bidi embeddings and overrides
        *range(0x2060, 0x2065),  # word joiner and invisible operators
        *range(0x2066, 0x206A),  # bidi isolates
        0xFEFF,  # zero-width no-break space / BOM
    ],
    None,
)
_WHITESPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize(text: str) -> str:
    """Return ``text`` in the canonical form detection rules run against."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_INVISIBLE)
    text = _CONTROL.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def collapse(text: str) -> str:
    """Collapse whitespace without any other change."""
    return _WHITESPACE.sub(" ", text).strip()
