from dramamemory_data.search.documents import DramaSource, render_drama, row_to_source


def _goblin(**kw) -> DramaSource:
    base = dict(
        id=4, slug="guardian-the-lonely-and-great-god", title_ko="도깨비",
        title_en="Guardian: The Lonely and Great God",
        aliases=["Goblin", "쓸쓸하고 찬란하神 도깨비"],
        broadcaster_code="tvn", broadcaster_name="tvN",
        start_date="2016-12-02", end_date="2017-01-21",
        episode_count=16, synopsis="불멸의 도깨비와 저승사자", genres=["fantasy", "romance"],
        cast=[("공유", "김신"), ("김고은", "지은탁")],
        crew=[("이응복", "DIRECTOR"), ("김은숙", "WRITER")],
        osts=[("Stay With Me", ["찬열", "펀치"]), ("Beautiful", ["크러쉬"])], canonical_version=2,
    )
    base.update(kw)
    return DramaSource(**base)


def test_render_body_uses_human_words():
    doc = render_drama(_goblin())
    assert doc.entity_type == "DRAMA" and doc.entity_id == 4
    assert doc.title == "도깨비"
    assert doc.aliases == "Guardian: The Lonely and Great God\nGoblin\n쓸쓸하고 찬란하神 도깨비"
    assert doc.body.splitlines() == [
        "방송사: tvN",
        "연도: 2016년",
        "장르: 판타지, 로맨스",
        "출연: 공유 (김신 역), 김고은 (지은탁 역)",
        "연출: 이응복",
        "극본: 김은숙",
        "OST: Stay With Me - 찬열, 펀치, Beautiful - 크러쉬",
        "줄거리: 불멸의 도깨비와 저승사자",
    ]
    assert doc.metadata["year"] == 2016
    assert doc.metadata["cast"] == ["공유", "김고은"]
    assert doc.metadata["document_version"] == 1


def test_hash_changes_only_with_content():
    a = render_drama(_goblin())
    b = render_drama(_goblin())
    c = render_drama(_goblin(synopsis="다른 줄거리"))
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash
    assert len(a.content_hash) == 64


def test_render_tolerates_missing_optional_fields():
    doc = render_drama(_goblin(
        title_en=None, aliases=[], broadcaster_code=None, broadcaster_name=None,
        start_date=None, synopsis=None, genres=[], cast=[], crew=[], osts=[],
    ))
    assert doc.aliases == ""
    assert doc.body == ""
    assert doc.metadata["year"] is None


def test_row_to_source_maps_sql_row():
    row = (4, "slug", "도깨비", None, ["Goblin"], "tvn", "tvN", "2016-12-02", None, 16, None,
           ["fantasy"], [["공유", "김신"]], [["김은숙", "WRITER"]], [["Stay With Me", ["찬열"]]], 3)
    s = row_to_source(row)
    assert s.cast == [("공유", "김신")]
    assert s.crew == [("김은숙", "WRITER")]
    assert s.osts == [("Stay With Me", ["찬열"])]
    assert s.canonical_version == 3
