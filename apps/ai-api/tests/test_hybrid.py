"""HybridRetriever with a fake store: verifies orchestration, filters, strategy, evidence."""

from ai_api.embedder import FakeEmbedder
from ai_api.retrieval.fusion import Candidate
from ai_api.retrieval.hybrid import HybridRetriever
from ai_api.retrieval.store import Doc


class FakeStore:
    def __init__(self):
        self.calls = []
        self.docs_by_id = {
            1: Doc(1, 4, "도깨비", ["Goblin"], "출연: 공유", {"slug": "goblin", "year": 2016}),
            2: Doc(2, 5, "시그널", ["Signal"], "출연: 김혜수", {"slug": "signal", "year": 2016}),
            3: Doc(3, 9, "호텔 델루나", [], "출연: 아이유", {"slug": "hotel", "year": 2019}),
        }

    def _c(self, *ids):
        return [Candidate(doc_id=d, rank=i + 1, score=1.0) for i, d in enumerate(ids)]

    def fts(self, text, filters, limit):
        self.calls.append(("fts", text, filters))
        if filters.get("year_from") == 1988:
            return []          # nothing aired in 1988: the "year" was part of a title
        return self._c(1) if "공유" in text else []

    def fts_any(self, text, filters, limit):
        self.calls.append(("fts_any", text, filters))
        if filters.get("year_from") == 1988:
            return []
        return self._c(2) if "1988" in text else []

    def trigram(self, text, filters, limit):
        self.calls.append(("trigram", text, filters))
        return self._c(1) if text.startswith("도깨") else []

    def vector(self, vec, filters, limit):
        self.calls.append(("vector", None, filters))
        if filters.get("year_from") == 1988:
            return []
        return self._c(3, 1)

    def vector_synopsis(self, vec, filters, limit):
        self.calls.append(("vector_synopsis", None, filters))
        if filters.get("year_from") == 1988:
            return []
        return self._c(1)

    def filter_only(self, filters, limit):
        self.calls.append(("filter", None, filters))
        return self._c(1, 2)

    def docs(self, ids):
        return {i: self.docs_by_id[i] for i in ids if i in self.docs_by_id}


FAKE = FakeEmbedder(dim=8)


def _retriever(store=None, embedder=FAKE):
    return HybridRetriever(store or FakeStore(), embedder, rrf_k=60, candidates=10)


def test_hybrid_fuses_and_reports_evidence():
    r = _retriever()
    res = r.search("공유 판타지", limit=5)
    assert res.strategy == "hybrid"
    assert res.lists == {"fts": 1, "fts_any": 0, "trigram": 0, "vector": 2, "vector_synopsis": 1}
    assert [h.drama_id for h in res.hits] == [4, 9]        # 4 in three lists beats 9 (vector only)
    assert res.hits[0].ranks == {"fts": 1, "vector": 2, "vector_synopsis": 1}
    assert res.hits[0].metadata["slug"] == "goblin"
    assert set(res.latency_ms) >= {"fts", "trigram", "embed", "vector", "fuse"}
    assert res.embedding_model == "fake/hash-embedder"


def test_constraints_become_filters_and_stripped_text():
    store = FakeStore()
    _retriever(store).search("2016년 tvN 공유")
    name, text, filters = store.calls[0]
    assert name == "fts" and text == "공유"
    assert filters == {"year_from": 2016, "year_to": 2016, "broadcaster": "tvn"}


def test_explicit_filters_override_the_text():
    store = FakeStore()
    res = _retriever(store).search("2016년 공유", year_from=2018, year_to=2019, broadcaster="KBS")
    _, text, filters = store.calls[0]
    assert text == "공유"
    assert filters == {"year_from": 2018, "year_to": 2019, "broadcaster": "kbs"}
    assert res.plan.signals["explicit"] == "broadcaster,year_from,year_to"
    # a single bound fills the other side so the window is well-formed
    store = FakeStore()
    _retriever(store).search("공유", year_from=2010)
    assert store.calls[0][2] == {"year_from": 2010, "year_to": 2010, "broadcaster": None}


def test_modes_skip_retrievers():
    store = FakeStore()
    res = _retriever(store).search("공유", use_vector=False)
    assert res.strategy == "lexical" and "vector" not in res.lists
    store = FakeStore()
    res = _retriever(store).search("공유", use_lexical=False)
    assert res.strategy == "vector" and "fts" not in res.lists


def test_constraint_only_query_falls_back_to_filter():
    store = FakeStore()
    r = _retriever(store, embedder=None)
    res = r.search("2016 tvn")   # constraints only: retrievers are skipped entirely
    assert res.strategy == "filter"
    assert [c[0] for c in store.calls] == ["filter"]
    assert [h.drama_id for h in res.hits] == [4, 5]


def test_title_number_mistaken_for_year_is_relaxed():
    store = FakeStore()
    res = _retriever(store).search("응답하라 1988")
    assert res.relaxed is True
    assert res.plan.year_from is None and res.plan.text == "응답하라 1988"
    # first pass filtered by 1988 (empty), second pass without constraints
    years = [c[2].get("year_from") for c in store.calls]
    assert years[0] == 1988 and years[-1] is None
    assert 5 in [h.drama_id for h in res.hits]   # fts_any found it on the relaxed pass


def test_no_embedder_means_lexical_only():
    res = _retriever(embedder=None).search("공유")
    assert res.strategy == "lexical"
    assert res.embedding_model is None
