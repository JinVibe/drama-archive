from dramamemory_data.discovery import wikidata as disc

TV_SERIES = "Q5398426"


def _details(**per_qid):
    out = {}
    for qid, d in per_qid.items():
        out[qid] = {
            "label": d.get("label"),
            "classes": set(d.get("classes", ())),
            "genre_labels": list(d.get("genres", ())),
            "countries": set(d.get("countries", ())),
            "article": d.get("article"),
        }
    return out


def _run(sparql, kowiki, details):
    cands = disc.build_candidates(sparql, kowiki, details)
    for c in cands.values():
        c.decide()
    return cands, disc.decide(cands)


def test_year_categories():
    assert disc.year_categories(2006, 2008) == [
        "분류:2006년 텔레비전 드라마",
        "분류:2007년 텔레비전 드라마",
        "분류:2008년 텔레비전 드라마",
    ]


def test_union_and_verdicts():
    sparql = {"Q1", "Q2", "Q3"}
    kowiki = {
        "로스쿨 (드라마)": {
            "qid": "Q4",
            "categories": ["2021년 텔레비전 드라마", "JTBC 수목드라마"],
        },
        "경감 메그레": {
            "qid": "Q5",
            "categories": ["2016년 텔레비전 드라마", "KBS에서 방영한 프로그램"],
        },
        "무명 페이지": {"qid": None, "categories": []},
    }
    details = _details(
        Q1={
            "label": "도깨비",
            "classes": [TV_SERIES],
            "genres": ["fantasy television series"],
            "countries": ["Q884"],
        },
        Q2={
            "label": "런닝맨",
            "classes": [TV_SERIES, "Q336181"],
            "genres": ["리얼리티 방송"],
            "countries": ["Q884"],
        },
        Q3={
            "label": "스트릿댄스 걸스 파이터",
            "classes": [TV_SERIES],
            "countries": ["Q884"],
            "article": "스트릿댄스 걸스 파이터",
        },
        Q4={"label": "로스쿨", "classes": [TV_SERIES], "countries": ["Q884"]},
        Q5={"label": "Maigret", "classes": [TV_SERIES], "countries": ["Q145"]},
    )
    cands, (items, excluded) = _run(sparql, kowiki, details)

    assert cands["Q4"].found_by == {"kowiki"} and cands["Q1"].found_by == {"sparql"}
    assert [i["external_id"] for i in items] == ["Q1", "Q3", "Q4"]
    assert {i["external_id"]: i["kind"] for i in items} == {
        "Q1": "DRAMA",
        "Q3": "UNKNOWN",
        "Q4": "DRAMA",
    }
    assert items[0]["url"].startswith("https://query.wikidata.org/sparql?")
    assert [(e["external_id"], e["reason"]) for e in excluded] == [
        ("Q2", "not_a_drama"),
        ("Q5", "foreign"),
    ]

    # The ambiguous one is the only candidate that needs its categories looked up.
    assert [c.qid for c in cands.values() if disc.needs_category_lookup(c)] == ["Q3"]
    cands["Q3"].kowiki_categories = [
        "2021년 대한민국의 텔레비전 예능 프로그램",
        "Mnet의 예능 프로그램",
    ]
    cands["Q3"].decide()
    items, excluded = disc.decide(cands)
    assert [i["external_id"] for i in items] == ["Q1", "Q4"]
    q3 = next(e for e in excluded if e["external_id"] == "Q3")
    assert q3["reason"] == "not_a_drama" and q3["signals"][0].startswith("kowiki category")


def test_kowiki_only_page_needs_a_korean_category_when_country_is_unknown():
    kowiki = {
        "어떤 일본 드라마": {
            "qid": "Q7",
            "categories": ["2016년 텔레비전 드라마", "후지 TV 드라마"],
        },
        "어떤 한국 드라마": {
            "qid": "Q8",
            "categories": ["2016년 텔레비전 드라마", "SBS 월화드라마"],
        },
    }
    _, (items, excluded) = _run(set(), kowiki, _details(Q7={"classes": [TV_SERIES]}, Q8={}))
    assert [i["external_id"] for i in items] == ["Q8"]
    assert excluded[0]["external_id"] == "Q7" and excluded[0]["reason"] == "foreign"


def test_merge_detail_rows():
    out = {}
    base = {
        "item": {"value": "http://www.wikidata.org/entity/Q1"},
        "itemLabel": {"value": "도깨비"},
    }
    disc.merge_detail_row(
        out,
        {
            **base,
            "cls": {"value": "http://www.wikidata.org/entity/Q5398426"},
            "genreLabel": {"value": "판타지"},
            "country": {"value": "http://www.wikidata.org/entity/Q884"},
            "article": {
                "value": "https://ko.wikipedia.org/wiki/%EB%8F%84%EA%B9%A8%EB%B9%84_(%EB%93%9C%EB%9D%BC%EB%A7%88)"
            },
        },
    )
    disc.merge_detail_row(out, {**base, "genreLabel": {"value": "판타지"}})
    assert out["Q1"] == {
        "label": "도깨비",
        "classes": {"Q5398426"},
        "genre_labels": ["판타지"],
        "countries": {"Q884"},
        "article": "도깨비 (드라마)",
    }
