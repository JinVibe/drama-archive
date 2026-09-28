import json
from datetime import date

import pytest

from dramamemory_data.parsers import parser_for
from dramamemory_data.parsers.wikidata_sparql import (
    PARSER_VERSION,
    WikidataParseError,
    detail_url,
    genre_codes,
    parse,
)

ITEM = "http://www.wikidata.org/entity/Q24859151"


def _row(p, o, *, o_type="literal", label=None, char=None, birth=None, ord_=None, lang=None):
    r = {
        "item": {"type": "uri", "value": ITEM},
        "p": {
            "type": "uri" if p.startswith("P") else "literal",
            "value": f"http://www.wikidata.org/prop/{p}" if p.startswith("P") else p,
        },
        "o": {"type": o_type, "value": o},
    }
    if label is not None:
        r["oLabel"] = {"type": "literal", "value": label}
    if char is not None:
        r["charLabel"] = {"type": "literal", "value": char}
    if birth is not None:
        r["birth"] = {"type": "literal", "value": birth}
    if ord_ is not None:
        r["ord"] = {"type": "literal", "value": ord_}
    if lang is not None:
        r["lang"] = {"type": "literal", "value": lang}
    return r


def _doc(rows) -> bytes:
    return json.dumps({"results": {"bindings": rows}}, ensure_ascii=False).encode("utf-8")


GOBLIN = [
    _row("label", "쓸쓸하고 찬란하神 - 도깨비", lang="ko"),
    _row("label", "Guardian: The Lonely and Great God", lang="en"),
    _row("alias", "도깨비", lang="ko"),
    _row("alias", "Goblin", lang="en"),
    _row("alias", "-sseul-ha-go cha-ran-ha-sin-do-ggae-bi", lang="en"),
    _row("alias", "Пхурын падаи чонсоль", lang="en"),  # normalizes to "" -> dropped
    _row("P1476", "쓸쓸하고 찬란하神-도깨비", label="쓸쓸하고 찬란하神-도깨비"),
    _row("P580", "2016-12-02T00:00:00Z", label="2016-12-02T00:00:00Z"),
    _row("P582", "2017-01-21T00:00:00Z", label="2017-01-21T00:00:00Z"),
    _row("P1113", "16", label="16"),
    _row("P449", "http://www.wikidata.org/entity/Q333424", o_type="uri", label="tvN"),
    _row(
        "P136",
        "http://www.wikidata.org/entity/Q84270297",
        o_type="uri",
        label="romance television series",
    ),
    _row(
        "P136",
        "http://www.wikidata.org/entity/Q98526245",
        o_type="uri",
        label="fantasy television series",
    ),
    _row("P136", "http://www.wikidata.org/entity/Q1366112", o_type="uri", label="텔레비전 드라마"),
    _row(
        "P161",
        "http://www.wikidata.org/entity/Q623436",
        o_type="uri",
        label="공유",
        char="김신",
        birth="1979-07-10T00:00:00Z",
        ord_="1",
    ),
    _row(
        "P161",
        "http://www.wikidata.org/entity/Q6408653",
        o_type="uri",
        label="김고은",
        birth="1991-07-02T00:00:00Z",
    ),
    _row(
        "P161",
        "http://www.wikidata.org/entity/Q6408653",
        o_type="uri",
        label="김고은",
        birth="1991-07-02T00:00:00Z",
    ),  # duplicate row
    _row(
        "P161", "http://www.wikidata.org/entity/Q99999999", o_type="uri", label="Q99999999"
    ),  # unlabeled person
    _row(
        "P58",
        "http://www.wikidata.org/entity/Q7205130",
        o_type="uri",
        label="김은숙",
        birth="1973-01-01T00:00:00Z",
    ),
]


def test_parse_goblin():
    d = parse(_doc(GOBLIN))
    assert d.external_id == "Q24859151"
    assert d.title_ko == "쓸쓸하고 찬란하神 - 도깨비"
    assert d.title_en == "Guardian: The Lonely and Great God"
    # original title collapses onto the label after normalization (神 and spacing drop out);
    # romanization junk starting with '-' is dropped
    assert [a.alias for a in d.aliases] == ["도깨비", "Goblin"]
    assert "도깨비" in [a.alias_normalized for a in d.aliases]
    assert d.broadcaster_code == "tvn"
    assert (d.start_date, d.end_date, d.episode_count) == (date(2016, 12, 2), date(2017, 1, 21), 16)
    assert d.genres == ["fantasy", "romance"]
    assert [(c.person.external_id, c.person.name_ko, c.credit_type) for c in d.credits] == [
        ("Q623436", "공유", "ACTOR"),
        ("Q6408653", "김고은", "ACTOR"),
        ("Q7205130", "김은숙", "WRITER"),
    ]
    gong = d.credits[0]
    assert gong.character_name == "김신" and gong.billing_order == 1 and gong.is_main_cast is True
    assert gong.person.birth_date == date(1979, 7, 10)
    assert d.credits[1].billing_order is None and d.credits[1].is_main_cast is False
    assert d.synopsis is None and d.links == []


def test_title_falls_back_to_original_then_english():
    rows = [r for r in GOBLIN if r["p"]["value"] != "label"]
    d = parse(_doc(rows))
    assert d.title_ko == "쓸쓸하고 찬란하神-도깨비" and d.title_en is None
    assert [a.alias for a in d.aliases] == ["도깨비", "Goblin"]
    rows = [r for r in rows if not r["p"]["value"].endswith("P1476")] + [
        _row("label", "Goblin EN", lang="en")
    ]
    assert parse(_doc(rows)).title_ko == "Goblin EN"


def test_unknown_value_birth_date_is_tolerated():
    rows = GOBLIN + [
        _row(
            "P161",
            "http://www.wikidata.org/entity/Q77777",
            o_type="uri",
            label="미상배우",
            birth="http://www.wikidata.org/.well-known/genid/abc",
        )
    ]
    d = parse(_doc(rows))
    unknown = [c for c in d.credits if c.person.external_id == "Q77777"][0]
    assert unknown.person.birth_date is None


def test_unknown_broadcaster_becomes_none():
    rows = [
        r
        if not r["p"]["value"].endswith("P449")
        else _row("P449", "http://www.wikidata.org/entity/Q1", o_type="uri", label="Unknown TV")
        for r in GOBLIN
    ]
    assert parse(_doc(rows)).broadcaster_code is None


@pytest.mark.parametrize("bad", [b"<html>", b"{}", b'{"results":{"bindings":[]}}'])
def test_parse_rejects(bad):
    with pytest.raises(WikidataParseError):
        parse(bad)


def test_genre_keywords():
    assert genre_codes(["로맨틱 코미디 텔레비전 시리즈"]) == ["comedy", "romance"]
    assert genre_codes(["Korean historical drama", "스릴러", "텔레비전 드라마"]) == [
        "historical",
        "thriller",
    ]
    assert genre_codes([]) == []


def test_registry_and_url():
    version, fn = parser_for("wikidata")
    assert version == PARSER_VERSION and fn is parse
    url = detail_url("Q24859151")
    assert (
        url.startswith("https://query.wikidata.org/sparql?format=json&query=")
        and "Q24859151" in url
    )


def test_program_kind_from_classes_and_genres():
    series = _row(
        "P31", "http://www.wikidata.org/entity/Q5398426", o_type="uri", label="텔레비전 시리즈"
    )
    assert parse(_doc(GOBLIN + [series])).program_kind == "DRAMA"

    variety = [
        _row("label", "런닝맨", lang="ko"),
        series,
        _row("P31", "http://www.wikidata.org/entity/Q336181", o_type="uri", label="버라이어티 쇼"),
        _row("P136", "http://www.wikidata.org/entity/Q182415", o_type="uri", label="리얼리티 방송"),
    ]
    assert parse(_doc(variety)).program_kind == "NOT_DRAMA"

    bare = [_row("label", "스트릿댄스 걸스 파이터", lang="ko"), series]
    assert parse(_doc(bare)).program_kind == "UNKNOWN"


def test_original_network_wins_over_streaming_platform():
    rows = [
        _row("label", "동백꽃 필 무렵", lang="ko"),
        _row("P449", "http://www.wikidata.org/entity/Q907311", o_type="uri", label="넷플릭스"),
        _row("P449", "http://www.wikidata.org/entity/Q498825", o_type="uri", label="KBS"),
    ]
    assert parse(_doc(rows)).broadcaster_code == "kbs"
    only_ott = [rows[0], rows[1]]
    assert parse(_doc(only_ott)).broadcaster_code == "netflix"
