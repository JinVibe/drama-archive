"""Text normalization used for matching keys and slugs.

Normalized keys are for *comparison only*; display strings are stored separately.
"""

from __future__ import annotations

import re
import unicodedata

_NON_KEY_CHARS = re.compile(r"[^0-9a-z가-힣ㄱ-ㆎ]+")
_NON_SLUG_CHARS = re.compile(r"[^0-9a-z가-힣]+")
_WS = re.compile(r"\s+")


def clean(value: str | None) -> str | None:
    """Trim, collapse whitespace, NFKC-fold. Returns None for empty input."""
    if value is None:
        return None
    text = _WS.sub(" ", unicodedata.normalize("NFKC", value)).strip()
    return text or None


def normalize_key(value: str | None) -> str:
    """Lowercase, drop punctuation *and* whitespace so '또 오해영' == '또오해영'.

    Keeps Hangul syllables/jamo, ASCII letters and digits.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    return _NON_KEY_CHARS.sub("", text)


def normalize_broadcaster(value: str | None) -> str:
    """'tvN ' -> 'tvn'. Matches broadcaster.code."""
    return normalize_key(value)


def slugify(value: str) -> str:
    """URL slug that keeps Hangul.

    '도깨비' -> '도깨비', 'Guardian: The Lonely' -> 'guardian-the-lonely'.
    """
    text = unicodedata.normalize("NFKC", value).casefold()
    text = _NON_SLUG_CHARS.sub("-", text).strip("-")
    return text or "untitled"
