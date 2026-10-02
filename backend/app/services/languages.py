"""Languages ShadowPrompt covers beyond English, shared by ShadowScan and the Lab.

ShadowScan has detection rules in each of these languages, and the Lab has an
opt-in pack of tests written in them. Attacks in a language other than the one
a model was mostly aligned in are a well-documented way around its guardrails,
and hidden page instructions are not always in English either.
"""

from __future__ import annotations

ENGLISH = "en"

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "hi": "Hindi",
    "ar": "Arabic",
}

# Languages beyond English, in display order.
EXTRA_LANGUAGES: tuple[str, ...] = tuple(code for code in LANGUAGE_NAMES if code != ENGLISH)

# Characters a text must contain before rules in that language are worth
# running. Latin-script languages have no cheap test, so they always run.
SCRIPT_HINTS: dict[str, str] = {
    "ru": "[Ѐ-ӿ]",
    "zh": "[一-鿿]",
    "ja": "[぀-ヿ一-鿿]",
    "hi": "[ऀ-ॿ]",
    "ar": "[؀-ۿ]",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)
