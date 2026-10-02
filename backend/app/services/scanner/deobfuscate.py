"""Decoded views of a segment, so encoded instructions are scanned too.

An attacker who knows a page will be read by an LLM can hide an instruction
from rule-based scanners by encoding it: the model decodes Base64 or reads
leetspeak happily, but a regex looking for "ignore previous instructions"
never sees those words. This module produces alternative readings of a
segment's text, each labelled with the transform that produced it:

* **Byte encodings**: Base64 (standard and URL-safe), hexadecimal, ``\\x`` and
  ``\\u`` escapes, numeric HTML character references, and percent encoding.
  Decoded bytes must be readable UTF-8 text, so images, hashes and other binary
  blobs are discarded.
* **Letter games**: ROT13 and reversed text, kept only when the transformed text
  reads more like English than the original did, plus leetspeak (``1gn0r3``)
  and letters split by punctuation (``i.g.n.o.r.e``).
* **Look-alike characters**: Cyrillic and Greek letters that are visually
  identical to Latin ones, folded to Latin when they are mixed into Latin text.

Decoders are applied twice at most, so Base64 wrapped around ROT13 is still
found, and every step is bounded so a hostile page cannot turn decoding into a
CPU or memory sink. Nothing is executed; decoding is pure string handling.
"""

from __future__ import annotations

import base64
import binascii
import html
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from app.services.scanner.normalize import normalize

MAX_DEPTH = 2
MAX_VARIANTS_PER_SEGMENT = 8
MAX_CANDIDATES_PER_DECODER = 16
MIN_DECODED_CHARS = 8
MIN_PRINTABLE_RATIO = 0.9

TRANSFORM_LABELS: dict[str, str] = {
    "base64": "Base64",
    "hex": "hexadecimal",
    "escape": "escape sequences",
    "entity": "HTML character references",
    "url": "URL encoding",
    "rot13": "ROT13",
    "reversed": "reversed text",
    "leetspeak": "leetspeak",
    "separated": "letters split by punctuation",
    "homoglyph": "look-alike characters",
    "split": "fragments split across elements",
}


def transform_label(transform: str) -> str:
    """Human label for a transform chain such as ``base64>rot13``."""
    return ", then ".join(TRANSFORM_LABELS.get(step, step) for step in transform.split(">"))


@dataclass(frozen=True)
class Variant:
    """One decoded reading of a segment."""

    transform: str
    text: str


# --------------------------------------------------------------------------- #
# Byte encodings
# --------------------------------------------------------------------------- #

_BASE64 = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{16,}={0,2}(?![A-Za-z0-9+/=_-])")
_HEX_RUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){8,}(?![0-9A-Fa-f])")
_HEX_SPACED = re.compile(
    r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[ :,]){7,}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])"
)
_ESCAPES = re.compile(r"(?:\\x[0-9A-Fa-f]{2}|\\u[0-9A-Fa-f]{4}){4,}")
_ENTITIES = re.compile(r"(?:&#(?:[0-9]{1,7}|[xX][0-9A-Fa-f]{1,6});){4,}")
_PERCENT = re.compile(r"%[0-9A-Fa-f]{2}")


def _readable(raw: bytes) -> str | None:
    """Decoded bytes as text, or None if they are not readable text."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if len(text) < MIN_DECODED_CHARS:
        return None
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\t")
    if printable / len(text) < MIN_PRINTABLE_RATIO:
        return None
    # Text, not an identifier: at least one gap between words and a few letters.
    if not any(ch.isspace() for ch in text) or sum(ch.isalpha() for ch in text) < 4:
        return None
    return text


def _decode_base64(token: str) -> str | None:
    stripped = token.rstrip("=")
    padded = stripped + "=" * (-len(stripped) % 4)
    decoder = base64.urlsafe_b64decode if ("-" in token or "_" in token) else base64.b64decode
    try:
        raw = decoder(padded)
    except (binascii.Error, ValueError):
        return None
    return _readable(raw)


def _base64(text: str) -> list[str]:
    found = []
    for match in _BASE64.finditer(text):
        decoded = _decode_base64(match.group())
        if decoded:
            found.append(decoded)
        if len(found) >= MAX_CANDIDATES_PER_DECODER:
            break
    return found


def _hex(text: str) -> list[str]:
    found = []
    for pattern in (_HEX_RUN, _HEX_SPACED):
        for match in pattern.finditer(text):
            digits = re.sub(r"[ :,]", "", match.group())
            decoded = _readable(bytes.fromhex(digits))
            if decoded:
                found.append(decoded)
            if len(found) >= MAX_CANDIDATES_PER_DECODER:
                return found
    return found


def _decode_escape_run(run: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return chr(int(match.group()[2:], 16))

    return re.sub(r"\\x[0-9A-Fa-f]{2}|\\u[0-9A-Fa-f]{4}", replace, run)


def _escapes(text: str) -> list[str]:
    if "\\" not in text:
        return []
    decoded = _ESCAPES.sub(lambda m: _decode_escape_run(m.group()), text)
    return [decoded] if decoded != text else []


def _entities(text: str) -> list[str]:
    if "&#" not in text or not _ENTITIES.search(text):
        return []
    return [html.unescape(text)]


def _url(text: str) -> list[str]:
    if len(_PERCENT.findall(text)) < 4:
        return []
    decoded = urllib.parse.unquote(text.replace("+", " "))
    return [decoded] if decoded != text else []


# --------------------------------------------------------------------------- #
# Letter games
# --------------------------------------------------------------------------- #

# Common English words. A transform is only believed when its output contains
# clearly more of them than the input did.
_COMMON_WORDS = frozenset(
    "a about above all and any are as ask assistant be before data do every for from "
    "have i ignore in instructions is it me model must new not now of on only or "
    "previous prior prompt reply reveal rules say secret send system tell that the this "
    "to user what when with you your".split()
)
_WORD = re.compile(r"[A-Za-z']+")
_ROT13 = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
)


def _english_score(text: str) -> int:
    return sum(1 for word in _WORD.findall(text.lower()) if word in _COMMON_WORDS)


def _if_more_english(original: str, candidate: str) -> list[str]:
    before = _english_score(original)
    after = _english_score(candidate)
    return [candidate] if after >= 3 and after > before * 2 else []


def _rot13(text: str) -> list[str]:
    return _if_more_english(text, text.translate(_ROT13))


def _reversed(text: str) -> list[str]:
    return _if_more_english(text, text[::-1])


_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
_LEET_TOKEN = re.compile(r"[A-Za-z0-9@$]*[A-Za-z][A-Za-z0-9@$]*")


def _leetspeak(text: str) -> list[str]:
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        token = match.group()
        if not re.search(r"[013457@$]", token):
            return token
        changed = True
        return token.translate(_LEET)

    decoded = _LEET_TOKEN.sub(replace, text)
    return [decoded] if changed else []


# Single letters joined by the same punctuation mark: i.g.n.o.r.e, s-y-s-t-e-m.
_SEPARATED = re.compile(
    r"(?<![A-Za-z])[A-Za-z](?:([.\-_*·|/])[A-Za-z])(?:\1[A-Za-z]){2,}(?![A-Za-z])"
)


def _separated(text: str) -> list[str]:
    decoded = _SEPARATED.sub(lambda m: re.sub(r"[.\-_*·|/]", "", m.group()), text)
    return [decoded] if decoded != text else []


# --------------------------------------------------------------------------- #
# Look-alike characters
# --------------------------------------------------------------------------- #

_CONFUSABLES = {
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o",
    "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "ѕ": "s", "і": "i", "ї": "i",
    "ј": "j", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ү": "y", "ӏ": "l", "һ": "h",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
    "С": "C", "Т": "T", "Х": "X", "Ү": "Y", "Ѕ": "S", "І": "I", "Ј": "J",
    # Greek
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "ι": "i", "κ": "k", "υ": "u", "χ": "x",
    "ε": "e", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    # Latin lookalikes NFKC leaves alone
    "ı": "i", "ȷ": "j", "ɡ": "g", "ɑ": "a", "ʟ": "L",
}  # fmt: skip
_CONFUSABLE_TABLE = str.maketrans(_CONFUSABLES)
_TOKEN = re.compile(r"\w+")


def _is_latin(ch: str) -> bool:
    return "a" <= ch.lower() <= "z"


def _homoglyph(text: str) -> list[str]:
    if not any(ch in _CONFUSABLES for ch in text):
        return []
    letters = [ch for ch in text if ch.isalpha()]
    latin = sum(1 for ch in letters if _is_latin(ch))
    if letters and latin / len(letters) >= 0.6:
        # Mostly Latin text with foreign letters mixed in: fold them all.
        decoded = text.translate(_CONFUSABLE_TABLE)
    else:
        # Genuine non-Latin text. Only fold words that mix scripts, which no
        # real word in Russian or Greek does.
        def fold(match: re.Match[str]) -> str:
            token = match.group()
            if any(_is_latin(ch) for ch in token) and any(ch in _CONFUSABLES for ch in token):
                return token.translate(_CONFUSABLE_TABLE)
            return token

        decoded = _TOKEN.sub(fold, text)
    return [decoded] if decoded != text else []


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

_DECODERS: tuple[tuple[str, Callable[[str], list[str]]], ...] = (
    ("base64", _base64),
    ("hex", _hex),
    ("escape", _escapes),
    ("entity", _entities),
    ("url", _url),
    ("rot13", _rot13),
    ("reversed", _reversed),
    ("leetspeak", _leetspeak),
    ("separated", _separated),
    ("homoglyph", _homoglyph),
)


def variants(text: str) -> list[Variant]:
    """Decoded readings of ``text`` (already normalised), most direct first."""
    out: list[Variant] = []
    seen = {text}
    frontier = [Variant("", text)]
    for _ in range(MAX_DEPTH):
        next_frontier: list[Variant] = []
        for parent in frontier:
            for name, decoder in _DECODERS:
                for decoded in decoder(parent.text):
                    decoded = normalize(decoded)
                    if decoded in seen:
                        continue
                    seen.add(decoded)
                    chain = f"{parent.transform}>{name}" if parent.transform else name
                    variant = Variant(chain, decoded)
                    out.append(variant)
                    next_frontier.append(variant)
                    if len(out) >= MAX_VARIANTS_PER_SEGMENT:
                        return out
        frontier = next_frontier
    return out
