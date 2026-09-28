from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ai_api.config import Settings, settings
from ai_api.db import make_pool
from ai_api.embedder import Embedder, build_embedder
from ai_api.graph.queries import GraphClient, Neo4jRunner
from ai_api.reranker import Reranker, build_reranker
from ai_api.retrieval.hybrid import HybridRetriever, SearchResult
from ai_api.retrieval.store import SearchStore

log = logging.getLogger("ai_api")


def parse_weights(spec: str | None) -> dict[str, float] | None:
    """'vector:0.5,graph:1.5' -> {'vector': 0.5, 'graph': 1.5}; None/'' -> None."""
    if not spec:
        return None
    out: dict[str, float] = {}
    for part in spec.split(","):
        name, _, value = part.strip().partition(":")
        if not name or not value:
            raise HTTPException(400, f"bad weight spec {part!r}; expected name:number")
        try:
            out[name] = float(value)
        except ValueError as exc:
            raise HTTPException(400, f"bad weight {value!r} for {name}") from exc
        if out[name] < 0:
            raise HTTPException(400, f"weight for {name} must be >= 0")
    return out


class State:
    embedder: Embedder | None = None
    retriever: HybridRetriever | None = None
    graph: GraphClient | None = None
    reranker: Reranker | None = None
    pool = None
    ready: bool = False


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings()
    state.pool = make_pool()
    state.pool.open()
    log.info("loading embedder kind=%s model=%s", s.embedder, s.embedding_model)
    state.embedder = build_embedder(
        s.embedder, s.embedding_model, s.embedding_dim, s.embed_batch_size
    )
    if state.embedder.dim != s.embedding_dim:
        raise RuntimeError(
            f"embedder dim {state.embedder.dim} != configured {s.embedding_dim}; "
            "search_document.embedding column would not match"
        )
    runner: Neo4jRunner | None = None
    if s.neo4j_uri:
        runner = Neo4jRunner(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
        try:
            runner.open()
            state.graph = GraphClient(runner)
            log.info("graph enabled uri=%s", s.neo4j_uri)
        except Exception as exc:  # graph is optional (ARCHITECTURE §11: Neo4j outage -> SQL/vector)
            log.warning("graph disabled: %s", exc)
            runner = None
    if s.reranker != "none":
        log.info("loading reranker kind=%s model=%s", s.reranker, s.reranker_model)
        state.reranker = build_reranker(s.reranker, s.reranker_model)
    state.retriever = HybridRetriever(
        SearchStore(state.pool), state.embedder, graph=state.graph, reranker=state.reranker,
        rrf_k=s.rrf_k, candidates=s.candidates_per_list,
        rerank_candidates=s.rerank_candidates, list_weights=parse_weights(s.list_weights),
        retrieval_version=s.retrieval_version,
    )
    state.ready = True
    log.info("ready")
    yield
    state.ready = False
    state.pool.close()
    if runner is not None:
        runner.close()


app = FastAPI(title="DramaMemory AI Query API", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------- health
@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "UP"}


@app.get("/health/ready")
def ready() -> dict[str, Any]:
    if not state.ready:
        raise HTTPException(503, "model not loaded")
    return {"status": "UP", "embedding_model": state.embedder.model_id, "dim": state.embedder.dim}


# ---------------------------------------------------------------------------- search
class HitOut(BaseModel):
    drama_id: int
    title: str
    metadata: dict[str, Any]
    score: float
    ranks: dict[str, int]
    scores: dict[str, float]


class PlanOut(BaseModel):
    text: str
    year_from: int | None
    year_to: int | None
    broadcaster: str | None
    signals: dict[str, str]


class GraphOut(BaseModel):
    mode: str
    persons: list[dict[str, Any]]


class SearchOut(BaseModel):
    query: str
    plan: PlanOut
    strategy: str
    relaxed: bool
    graph: GraphOut | None = None
    lists: dict[str, int]
    total: int
    hits: list[HitOut]
    latency_ms: dict[str, int]
    retrieval_version: str
    embedding_model: str | None
    reranker: str | None = None


def _to_out(r: SearchResult) -> SearchOut:
    return SearchOut(
        query=r.query,
        plan=PlanOut(text=r.plan.text, year_from=r.plan.year_from, year_to=r.plan.year_to,
                     broadcaster=r.plan.broadcaster, signals=r.plan.signals),
        strategy=r.strategy, relaxed=r.relaxed, lists=r.lists, total=len(r.hits),
        graph=GraphOut(mode=r.graph.mode, persons=r.graph.persons) if r.graph else None,
        hits=[HitOut(**h.__dict__) for h in r.hits],
        latency_ms=r.latency_ms, retrieval_version=r.retrieval_version,
        embedding_model=r.embedding_model, reranker=r.reranker,
    )


def retriever() -> HybridRetriever:
    if not state.ready or state.retriever is None:
        raise HTTPException(503, "not ready")
    return state.retriever


@app.get("/v1/search", response_model=SearchOut)
def search(
    q: str = Query(min_length=1, max_length=300),
    size: int = Query(10, ge=1, le=50),
    mode: str = Query("hybrid", pattern="^(hybrid|lexical|vector|nograph)$"),
    year_from: int | None = Query(None, ge=1950, le=2100),
    year_to: int | None = Query(None, ge=1950, le=2100),
    broadcaster: str | None = Query(None, max_length=40, pattern="^[a-z0-9_]+$"),
    rerank: bool = Query(False, description="cross-encoder rerank of the fused top-N "
                                            "(needs AI_API_RERANKER; ignored otherwise)"),
    w: str | None = Query(None, max_length=200,
                          description="evaluation only: per-list RRF weights 'vector:0.5,graph:2'"),
    r: HybridRetriever = Depends(retriever),
) -> SearchOut:
    """Retrieval only (no generation): ranked dramas with evidence per retriever.
    `mode` exists for evaluation: lexical / vector / nograph (lexical+vector) / hybrid (all).
    Explicit `year_from`/`year_to`/`broadcaster` override what the query text implies
    (structured callers such as the MCP server)."""
    result = r.search(
        q, limit=size,
        use_vector=mode != "lexical", use_lexical=mode != "vector",
        use_graph=mode == "hybrid", rerank=rerank,
        year_from=year_from, year_to=year_to, broadcaster=broadcaster,
        weights=parse_weights(w),
    )
    return _to_out(result)


# ---------------------------------------------------------------------------- graph
def graph() -> GraphClient:
    if state.graph is None:
        raise HTTPException(503, "graph read model unavailable")
    return state.graph


@app.get("/v1/graph/dramas/{drama_id}/related")
def related_dramas(
    drama_id: int, limit: int = Query(10, ge=1, le=50), g: GraphClient = Depends(graph)
):
    """Other dramas connected through cast/crew and through OST artists (GRAPH_MODEL §8)."""
    return {"drama_id": drama_id, **g.related(drama_id, limit=limit)}


@app.get("/v1/graph/persons/{person_id}/collaborators")
def collaborators(
    person_id: int, limit: int = Query(10, ge=1, le=50), g: GraphClient = Depends(graph)
):
    """Co-stars ranked by shared work count. A count, not a claim about real relationships."""
    return {"person_id": person_id, "collaborators": g.collaborators(person_id, limit=limit)}


# ---------------------------------------------------------------------------- internal
class EmbedIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)


class EmbedOut(BaseModel):
    model: str
    dim: int
    vectors: list[list[float]]


def _check_internal(
    x_internal_token: str | None = Header(default=None), s: Settings = Depends(settings)
):
    if s.internal_token and x_internal_token != s.internal_token:
        raise HTTPException(401, "bad internal token")


@app.post("/internal/embed", response_model=EmbedOut, dependencies=[Depends(_check_internal)])
def embed(body: EmbedIn) -> EmbedOut:
    """Used by the embedding_refresh DAG so the model lives in exactly one process."""
    if not state.ready or state.embedder is None:
        raise HTTPException(503, "not ready")
    vectors = state.embedder.embed(body.texts)
    return EmbedOut(model=state.embedder.model_id, dim=state.embedder.dim, vectors=vectors)
