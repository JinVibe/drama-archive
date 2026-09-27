from datetime import date

import pytest

from dramamemory_data.normalization.dates import DateParseError, parse_date
from dramamemory_data.normalization.text import clean, normalize_broadcaster, normalize_key, slugify


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  도깨비 ", "도깨비"),
        ("tvN ", "tvn"),
        ("또 오해영", "또오해영"),
        ("또오해영", "또오해영"),
        ("Guardian: The Lonely and Great God", "guardianthelonelyandgreatgod"),
        ("쓸쓸하고 찬란하神 도깨비", "쓸쓸하고찬란하도깨비"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_key(raw, expected):
    assert normalize_key(raw) == expected


def test_normalize_broadcaster():
    assert normalize_broadcaster("tvN ") == "tvn"
    assert normalize_broadcaster("JTBC") == "jtbc"


def test_clean_collapses_whitespace_and_nfkc():
    assert clean("  공  유 ") == "공 유"
    assert clean("ｔｖＮ") == "tvN"
    assert clean("   ") is None
    assert clean(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("도깨비", "도깨비"),
        ("Guardian: The Lonely and Great God", "guardian-the-lonely-and-great-god"),
        ("또 오해영", "또-오해영"),
        ("!!!", "untitled"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2016.12.02", date(2016, 12, 2)),
        ("2016-12-02", date(2016, 12, 2)),
        ("2016/1/2", date(2016, 1, 2)),
        ("2016년 12월 2일", date(2016, 12, 2)),
        ("2016년 5월 2일", date(2016, 5, 2)),
        ("20161202", date(2016, 12, 2)),
        ("2016-12-02T21:00:00+09:00", date(2016, 12, 2)),
        ("", None),
        (None, None),
        (date(2020, 1, 1), date(2020, 1, 1)),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["December 2, 2016", "2016.13.01", "2016"])
def test_parse_date_rejects(raw):
    with pytest.raises(DateParseError):
        parse_date(raw)
