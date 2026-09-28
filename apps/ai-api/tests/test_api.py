"""FastAPI surface with the fake embedder and a stubbed retriever (no database)."""

from fastapi.testclient import TestClient

from ai_api import main
from ai_api.embedder import FakeEmbedder
from ai_api.retrieval.hybrid import Hit, SearchResult
from ai_api.retrieval.query import analyze


class StubRetriever:
    retrieval_version = "test"

    def search(self, query, limit=10, *, use_vector=True, use_lexical=True, use_graph=True,
               rerank=False, year_from=None, year_to=None, broadcaster=None, weights=None):
        plan = analyze(query)
        hits = [Hit(drama_id=4, title="도깨비", metadata={"slug": "goblin"}, score=0.03,
                    ranks={"fts": 1}, scores={"fts": 0.5})]
        return SearchResult(query=query, plan=plan, strategy="lexical", lists={"fts": 1},
                            hits=hits[:limit], latency_ms={"fts": 1}, retrieval_version="test",
                            embedding_model="fake")


def _client(token: str = "") -> TestClient:
    main.state.embedder = FakeEmbedder(dim=8)
    main.state.retriever = StubRetriever()
    main.state.ready = True
    main.settings.cache_clear()
    import os

    os.environ["AI_API_INTERNAL_TOKEN"] = token
    return TestClient(main.app)


def test_search_shape():
    c = _client()
    r = c.get("/v1/search", params={"q": "2016년 공유", "size": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == {"text": "공유", "year_from": 2016, "year_to": 2016,
                            "broadcaster": None, "signals": {"year": "2016년 "}}
    assert body["total"] == 1 and body["hits"][0]["drama_id"] == 4
    assert body["strategy"] == "lexical"


def test_search_validation():
    c = _client()
    assert c.get("/v1/search", params={"q": ""}).status_code == 422
    assert c.get("/v1/search", params={"q": "x", "mode": "magic"}).status_code == 422
    assert c.get("/v1/search", params={"q": "x", "size": 500}).status_code == 422


def test_embed_internal_token():
    c = _client(token="secret")
    r = c.post("/internal/embed", json={"texts": ["도깨비"]})
    assert r.status_code == 401
    r = c.post(
        "/internal/embed",
        json={"texts": ["도깨비", "시그널"]},
        headers={"X-Internal-Token": "secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dim"] == 8 and len(body["vectors"]) == 2 and len(body["vectors"][0]) == 8
    assert body["model"] == "fake/hash-embedder"


def test_ready_and_live():
    c = _client()
    assert c.get("/health/live").json() == {"status": "UP"}
    assert c.get("/health/ready").json()["dim"] == 8
    main.state.ready = False
    assert c.get("/health/ready").status_code == 503
    assert c.get("/v1/search", params={"q": "x"}).status_code == 503
