import json
from datetime import date
from pathlib import Path

import pytest

from dramamemory_data.parsers import parser_for, registered_sources
from dramamemory_data.parsers.dramamemory_json import PARSER_VERSION, DramaJsonParseError, parse

SEED_DIR = Path(__file__).resolve().parents[1] / "seed" / "dramas"


def _doc(**overrides) -> bytes:
    base = {
        "format": "dramamemory.drama.v1",
        "external_id": "x-1",
        "title_ko": " 또 오해영 ",
        "title_en": "Another Miss Oh",
        "aliases": ["또오해영", "Another Miss Oh"],
        "broadcaster": "tvN ",
        "start_date": "2016년 5월 2일",
        "end_date": "2016.06.28",
        "episode_count": 18,
        "genres": ["Romance", "comedy", "romance"],
        "credits": [
            {"person": {"external_id": "eric", "name_ko": "에릭", "birth_date": "1979-02-16"},
             "character": "박도경", "billing_order": 1, "main": True},
            {"person": {"name_ko": "송현욱"}, "type": "DIRECTOR"},
        ],
        "ost": [
            {
                "title": "꿈처럼",
                "artists": ["벤", {"name": "작곡가", "role": "COMPOSER"}],
                "part_no": 1,
            }
        ],
        "links": [
            {"provider": "TVN", "url": " https://tvn.cjenm.com/x ", "type": "BROADCASTER_PAGE"}
        ],
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False).encode("utf-8")


def test_parse_normalizes_everything():
    d = parse(_doc())
    assert d.external_id == "x-1"
    assert d.title_ko == "또 오해영"
    assert d.title_normalized == "또오해영"
    assert d.broadcaster_code == "tvn"
    assert d.start_date == date(2016, 5, 2)
    assert d.end_date == date(2016, 6, 28)
    assert d.genres == ["comedy", "romance"]
    # alias identical to the title after normalization is dropped
    assert [a.alias for a in d.aliases] == ["Another Miss Oh"]

    actor, director = d.credits
    assert actor.person.external_id == "eric"
    assert actor.person.name_normalized == "에릭"
    assert actor.person.birth_date == date(1979, 2, 16)
    assert actor.credit_type == "ACTOR"
    assert actor.is_main_cast is True
    assert director.credit_type == "DIRECTOR"
    assert director.person.external_id is None

    song = d.osts[0]
    assert song.title_normalized == "꿈처럼"
    assert [(a.artist.name, a.role, a.sort_order) for a in song.artists] == [
        ("벤", "PERFORMER", 1),
        ("작곡가", "COMPOSER", 2),
    ]

    link = d.links[0]
    assert link.provider_code == "tvn"
    assert link.url == "https://tvn.cjenm.com/x"
    assert link.region_code == "KR"


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"format": "dramamemory.drama.v0"}, "unsupported format"),
        ({"title_ko": "   "}, "title_ko is empty"),
        ({"start_date": "언젠가"}, "start_date"),
        ({"credits": [{"person": {"name_ko": ""}}]}, "name_ko is empty"),
        ({"links": [{"provider": "x", "url": "u", "type": "PIRATE"}]}, "schema violation"),
    ],
)
def test_parse_rejects(overrides, match):
    with pytest.raises(DramaJsonParseError, match=match):
        parse(_doc(**overrides))


def test_parse_rejects_non_json():
    with pytest.raises(DramaJsonParseError, match="not valid UTF-8 JSON"):
        parse(b"<html>")


def test_registry():
    assert registered_sources() == ["local_seed", "manual"]
    version, fn = parser_for("manual")
    assert version == PARSER_VERSION and fn is parse
    with pytest.raises(KeyError):
        parser_for("tvn_official")


@pytest.mark.parametrize("path", sorted(SEED_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_seed_files_parse_and_match_filename(path):
    d = parse(path.read_bytes())
    assert d.external_id == path.stem
    assert d.broadcaster_code == "tvn"
    assert d.start_date and d.end_date and d.start_date <= d.end_date
    assert d.credits, "seed drama must have credits"
