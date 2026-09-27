"""Lenient date parsing for source strings: '2016.12.02', '2016-12-02', '2016년 12월 2일'."""

from __future__ import annotations

import re
from datetime import date

_PATTERNS = (
    re.compile(r"^\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"),
    re.compile(r"^\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?"),
    re.compile(r"^\s*(\d{4})(\d{2})(\d{2})\s*$"),
)


class DateParseError(ValueError):
    pass


def parse_date(value: str | date | None) -> date | None:
    """Return a date or None for blank input. Raises DateParseError on unrecognized text."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = value.strip()
    if not text:
        return None
    for pattern in _PATTERNS:
        match = pattern.match(text)
        if match:
            year, month, day = (int(g) for g in match.groups())
            try:
                return date(year, month, day)
            except ValueError as exc:
                raise DateParseError(f"invalid calendar date: {value!r}") from exc
    raise DateParseError(f"unrecognized date format: {value!r}")


def year_of(value: date | None) -> int | None:
    return value.year if value else None
