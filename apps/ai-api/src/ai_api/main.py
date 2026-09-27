from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ai_api.config import Settings, settings
from ai_api.db import make_pool
from ai_api.embedder import Embedder, build_embedder
from ai_api.retrieval.hybrid import HybridRetriever, SearchResult
from ai_api.retrieval.store import SearchStore

log = logging.getLogger("ai_api")


class State:
    embedder: Embedder | None = None
    retriever: HybridRetriever | None = None
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
    state.retriever = HybridRetriever(
        SearchStore(state.pool), state.embedder,
        rrf_k=s.rrf_k, candidates=s.candidates_per_list, retrieval_version=s.retrieval_version,
    )
    state.ready = True
    log.info("ready")
    yield
    state.ready = False
    state.pool.close()


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


class SearchOut(BaseModel):
    query: str
    plan: PlanOut
    strategy: str
    relaxed: bool
    lists: dict[str, int]
    total: int
    hits: list[HitOut]
    latency_ms: dict[str, int]
    retrieval_version: str
    embedding_model: str | None


def _to_out(r: SearchResult) -> SearchOut:
    return SearchOut(
        query=r.query,
        plan=PlanOut(text=r.plan.text, year_from=r.plan.year_from, year_to=r.plan.year_to,
                     broadcaster=r.plan.broadcaster, signals=r.plan.signals),
        strategy=r.strategy, relaxed=r.relaxed, lists=r.lists, total=len(r.hits),
        hits=[HitOut(**h.__dict__) for h in r.hits],
        latency_ms=r.latency_ms, retrieval_version=r.retrieval_version,
        embedding_model=r.embedding_model,
    )


def retriever() -> HybridRetriever:
    if not state.ready or state.retriever is None:
        raise HTTPException(503, "not ready")
    return state.retriever


@app.get("/v1/search", response_model=SearchOut)
def search(
    q: str = Query(min_length=1, max_length=300),
    size: int = Query(10, ge=1, le=50),
    mode: str = Query("hybrid", pattern="^(hybrid|lexical|vector)$"),
    r: HybridRetriever = Depends(retriever),
) -> SearchOut:
    """Retrieval only (no generation): ranked dramas with evidence per retriever.
    `mode` exists for evaluation (lexical baseline vs vector vs hybrid)."""
    result = r.search(q, limit=size, use_vector=mode != "lexical", use_lexical=mode != "vector")
    return _to_out(result)


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
