"""Hybrid retrieval orchestration — docs/RAG_DESIGN.md.

    analyze(query) -> constraints + text
    lexical (FTS, trigram) + vector candidates, each filtered by the constraints
    RRF -> ranked hits with evidence (which list, which rank, raw score)

No LLM on this path. Generation (DM-704) consumes the output of this module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ai_api.embedder import Embedder
from ai_api.retrieval.fusion import rrf
from ai_api.retrieval.query import QueryPlan, analyze
from ai_api.retrieval.store import Doc, SearchStore


@dataclass
class Hit:
    drama_id: int
    title: str
    metadata: dict[str, Any]
    score: float
    ranks: dict[str, int]
    scores: dict[str, float]


@dataclass
class SearchResult:
    query: str
    plan: QueryPlan
    strategy: str                   # "lexical" | "vector" | "hybrid" | "filter"
    lists: dict[str, int]           # list name -> candidate count
    hits: list[Hit]
    relaxed: bool = False           # constraints dropped after they produced nothing
    latency_ms: dict[str, int] = field(default_factory=dict)
    retrieval_version: str = ""
    embedding_model: str | None = None


class HybridRetriever:
    def __init__(self, store: SearchStore, embedder: Embedder | None, *,
                 rrf_k: int = 60, candidates: int = 50, retrieval_version: str = "hybrid-v1"):
        self.store = store
        self.embedder = embedder
        self.rrf_k = rrf_k
        self.candidates = candidates
        self.retrieval_version = retrieval_version

    def search(self, query: str, limit: int = 10, *, use_vector: bool = True,
               use_lexical: bool = True) -> SearchResult:
        plan = analyze(query)
        lists: dict[str, list] = {}
        latency: dict[str, int] = {}
        relaxed = False

        def timed(name, fn):
            t = time.perf_counter()
            lists[name] = fn()
            latency[name] = int((time.perf_counter() - t) * 1000)

        def gather(p: QueryPlan) -> None:
            filters = {"year_from": p.year_from, "year_to": p.year_to, "broadcaster": p.broadcaster}
            if use_lexical and p.text:
                timed("fts", lambda: self.store.fts(p.text, filters, self.candidates))
                timed("fts_any", lambda: self.store.fts_any(p.text, filters, self.candidates))
                timed("trigram", lambda: self.store.trigram(p.text, filters, self.candidates))
            if use_vector and self.embedder is not None and p.text:
                t = time.perf_counter()
                vec = self.embedder.embed([p.text])[0]
                latency["embed"] = latency.get("embed", 0) + int((time.perf_counter() - t) * 1000)
                timed("vector", lambda: self.store.vector(vec, filters, self.candidates))
            if not any(lists.values()) and p.has_constraints and not p.text:
                timed("filter", lambda: self.store.filter_only(filters, self.candidates))

        gather(plan)
        # A "year" that was really part of a title (응답하라 1988) filters everything out:
        # drop the constraints and try once more with the plain text.
        if not any(lists.values()) and plan.has_constraints and plan.text:
            lists.clear()
            plan = analyze(query, extract_constraints=False)
            relaxed = True
            gather(plan)

        t = time.perf_counter()
        fused = rrf(lists, k=self.rrf_k, limit=limit)
        docs = self.store.docs([f.doc_id for f in fused])
        latency["fuse"] = int((time.perf_counter() - t) * 1000)

        hits = [
            Hit(drama_id=d.drama_id, title=d.title, metadata=d.metadata, score=f.score,
                ranks=f.ranks, scores=f.scores)
            for f in fused if (d := docs.get(f.doc_id))
        ]
        return SearchResult(
            query=query, plan=plan, strategy=_strategy(lists), relaxed=relaxed,
            lists={k: len(v) for k, v in lists.items()}, hits=hits, latency_ms=latency,
            retrieval_version=self.retrieval_version,
            embedding_model=self.embedder.model_id if self.embedder else None,
        )


def _strategy(lists: dict[str, list]) -> str:
    lexical = bool(lists.get("fts") or lists.get("fts_any") or lists.get("trigram"))
    vector = bool(lists.get("vector"))
    if lexical and vector:
        return "hybrid"
    if lexical:
        return "lexical"
    if vector:
        return "vector"
    if lists.get("filter"):
        return "filter"
    return "none"


__all__ = ["Doc", "Hit", "HybridRetriever", "SearchResult"]
