from ai_api.graph.queries import GraphClient
from ai_api.retrieval.graph_candidates import graph_candidates, name_candidates


class FakeRunner:
    """Tiny in-memory graph: people -> dramas."""

    PEOPLE = {"공유": (1, "gong-yoo"), "이동욱": (2, "lee-dong-wook"), "김혜수": (3, "kim-hye-soo")}
    WORKS = {1: [4], 2: [4, 7], 3: [5]}  # person id -> drama ids
    DRAMAS = {
        4: ("goblin", "도깨비", 2016),
        5: ("signal", "시그널", 2016),
        7: ("other", "다른작품", 2019),
    }

    def __init__(self):
        self.calls = []

    def rows(self, cypher, **params):
        self.calls.append((cypher.strip().split("\n")[0], params))
        if "p.name IN $names" in cypher:
            return [
                {"id": pid, "name": n, "slug": s}
                for n, (pid, s) in self.PEOPLE.items()
                if n in params["names"]
            ]
        if "DRAMAS_SHARED" in cypher or "count(DISTINCT p) AS shared" in cypher:
            ids = params["ids"]
            shared = set.intersection(*(set(self.WORKS[i]) for i in ids))
            return [self._d(d) for d in sorted(shared)]
        if "(p:Person {canonical_id: $id})-[r:ACTED_IN" in cypher:
            return [self._d(d) | {"credit": "ACTED_IN"} for d in self.WORKS.get(params["id"], [])]
        return []

    def _d(self, d):
        slug, title, year = self.DRAMAS[d]
        return {"id": d, "slug": slug, "title": title, "year": year}


DOC_IDS = {4: 104, 5: 105, 7: 107}


def test_name_candidates_strips_particles():
    cands = name_candidates("공유랑 이동욱이랑 같이 나온 드라마")
    assert {"공유", "이동욱"} <= set(cands)  # particle-stripped names are present
    assert cands.index("공유랑") < cands.index("공유")  # original token first, then variants
    assert "김혜수" in name_candidates("김혜수와 이제훈")
    assert name_candidates("goblin 2016") == []


def test_two_people_yield_shared_dramas():
    client = GraphClient(FakeRunner())
    cands, match = graph_candidates(
        client, "공유랑 이동욱 같이 나온 드라마", doc_id_by_drama=DOC_IDS
    )
    assert match.mode == "shared"
    assert [p["name"] for p in match.persons] == ["공유", "이동욱"]
    assert [c.doc_id for c in cands] == [104]  # only 도깨비 is shared, 다른작품 is not
    assert cands[0].rank == 1


def test_one_person_yields_their_works():
    client = GraphClient(FakeRunner())
    cands, match = graph_candidates(client, "이동욱 나온 드라마", doc_id_by_drama=DOC_IDS)
    assert match.mode == "person"
    assert [c.doc_id for c in cands] == [104, 107]


def test_people_who_never_worked_together_fall_back_to_union():
    client = GraphClient(FakeRunner())
    cands, match = graph_candidates(client, "공유 김혜수", doc_id_by_drama=DOC_IDS)
    assert match.mode == "person"
    assert sorted(c.doc_id for c in cands) == [104, 105]


def test_no_person_in_query():
    client = GraphClient(FakeRunner())
    cands, match = graph_candidates(client, "무전기로 교신하는 드라마", doc_id_by_drama=DOC_IDS)
    assert cands == [] and match.mode == "none"


def test_client_limits_are_bounded():
    runner = FakeRunner()
    GraphClient(runner).dramas_of_person(2, limit=9999)
    assert runner.calls[-1][1]["limit"] == 50
    assert GraphClient(runner).dramas_shared_by([1]) == []  # needs at least two people
