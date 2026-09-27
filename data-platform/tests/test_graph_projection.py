import pytest

from dramamemory_data.graph.projection import (
    ArtistRef,
    CreditRef,
    DramaAggregate,
    IntegrityError,
    PersonRef,
    SongRef,
    aggregate_statements,
    check_integrity,
    dramas_to_rebuild,
    row_to_aggregate,
)


def _goblin() -> DramaAggregate:
    return DramaAggregate(
        id=4,
        slug="goblin",
        title="도깨비",
        title_en="Guardian",
        start_date="2016-12-02",
        end_date="2017-01-21",
        episode_count=16,
        canonical_version=2,
        broadcaster=("tvn", "tvN"),
        genres=[("fantasy", "판타지")],
        credits=[
            CreditRef(
                PersonRef(1, "gong-yoo", "공유", "Gong Yoo", "1979-07-10"), "ACTOR", "김신", 1, True
            ),
            CreditRef(
                PersonRef(2, "kim-eun-sook", "김은숙", None, None), "WRITER", None, None, False
            ),
        ],
        songs=[
            SongRef(
                9,
                "Stay With Me",
                "2016-12-03",
                1,
                None,
                [ArtistRef(5, "찬열", "PERFORMER", 1), ArtistRef(6, "펀치", "PERFORMER", 2)],
            )
        ],
    )


def test_aggregate_statements_replace_edges_then_recreate():
    stmts = aggregate_statements(_goblin())
    cyphers = [c for c, _ in stmts]
    # first statement upserts the drama and drops every edge around it
    assert "MERGE (d:Drama {canonical_id: $id})" in cyphers[0] and "DELETE r" in cyphers[0]
    assert stmts[0][1]["start_year"] == 2016 and stmts[0][1]["version"] == 2
    # then broadcaster, genre, credits (typed edges), song (drops PERFORMED), artists
    assert "AIRED_BY" in cyphers[1] and "HAS_GENRE" in cyphers[2]
    assert "[r:ACTED_IN]" in cyphers[3] and stmts[3][1]["character"] == "김신"
    assert "[r:WROTE]" in cyphers[4]
    assert "HAS_OST" in cyphers[5] and "DELETE pr" in cyphers[5]
    assert cyphers[6].count("PERFORMED") == 1 and stmts[6][1]["aid"] == 5
    assert len(stmts) == 8
    # identity rule: every node keyed by canonical id, never by name
    assert all("canonical_id" in c or "code" in c for c in cyphers)


def test_aggregate_without_optional_parts():
    d = DramaAggregate(
        id=1,
        slug="x",
        title="X",
        title_en=None,
        start_date=None,
        end_date=None,
        episode_count=None,
        canonical_version=1,
        broadcaster=None,
    )
    stmts = aggregate_statements(d)
    assert len(stmts) == 1 and stmts[0][1]["start_year"] is None


def test_row_to_aggregate_maps_sql_json():
    row = (
        4,
        "goblin",
        "도깨비",
        "Guardian",
        "2016-12-02",
        "2017-01-21",
        16,
        2,
        "tvn",
        "tvN",
        [["fantasy", "판타지"]],
        [[1, "gong-yoo", "공유", "Gong Yoo", "1979-07-10", "ACTOR", "김신", 1, True]],
        [[9, "Stay With Me", "2016-12-03", 1, None, [[5, "찬열", "PERFORMER", 1]]]],
    )
    d = row_to_aggregate(row)
    assert d.broadcaster == ("tvn", "tvN") and d.genres == [("fantasy", "판타지")]
    assert d.credits[0].person.name == "공유" and d.credits[0].is_main_cast is True
    assert d.songs[0].artists[0].name == "찬열"


def test_dramas_to_rebuild_picks_missing_and_stale():
    pg = {1: 1, 2: 3, 3: 1}
    graph = {1: 1, 2: 2}
    assert dramas_to_rebuild(pg, graph) == [2, 3]


def test_check_integrity():
    base = {
        "drama_count": 24,
        "orphans": 0,
        "dramas_without_broadcaster": 1,
        "max_person_degree": 3,
    }
    assert check_integrity(base, published_count=24) == ["1 dramas without AIRED_BY"]
    with pytest.raises(IntegrityError, match="published"):
        check_integrity({**base, "drama_count": 23}, published_count=24)
    with pytest.raises(IntegrityError, match="orphan"):
        check_integrity({**base, "orphans": 2}, published_count=24)
    assert check_integrity(
        {**base, "dramas_without_broadcaster": 0, "max_person_degree": 999}, published_count=24
    ) == ["person degree spike: 999 ACTED_IN edges"]
