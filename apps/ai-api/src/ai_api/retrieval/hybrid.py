"""Hybrid retrieval orchestration — docs/RAG_DESIGN.md.

    analyze(query) -> constraints + text
    lexical (FTS, trigram) + vector candidates, each filtered by the constraints
    RRF -> ranked hits with evidence (which list, which rank, raw score)

No LLM on this path. Generation (DM-704) consumes the output of this module.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any

from ai_api.embedder import Embedder
from ai_api.graph.queries import GraphClient
from ai_api.reranker import Reranker
from ai_api.retrieval.fusion import rrf
from ai_api.retrieval.graph_candidates import GraphMatch, graph_candidates
from ai_api.retrieval.query import QueryPlan, analyze
from ai_api.retrieval.store import Doc, SearchStore

log = logging.getLogger("ai_api.retrieval")


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
    graph: GraphMatch | None = None # people matched in the graph, if any
    latency_ms: dict[str, int] = field(default_factory=dict)
    retrieval_version: str = ""
    embedding_model: str | None = None
    reranker: str | None = None     # model id when the rerank list was applied


class HybridRetriever:
    def __init__(self, store: SearchStore, embedder: Embedder | None, *,
                 graph: GraphClient | None = None, reranker: Reranker | None = None,
                 rrf_k: int = 60, candidates: int = 50, rerank_candidates: int = 30,
                 list_weights: dict[str, float] | None = None,
                 retrieval_version: str = "hybrid-v1"):
        self.store = store
        self.embedder = embedder
        self.graph = graph
        self.reranker = reranker
        self.rrf_k = rrf_k
        self.list_weights = dict(list_weights or {})
        self.candidates = candidates
        self.rerank_candidates = rerank_candidates
        self.retrieval_version = retrieval_version

    def search(self, query: str, limit: int = 10, *, use_vector: bool = True,
               use_lexical: bool = True, use_graph: bool = True, rerank: bool = False,
               year_from: int | None = None, year_to: int | None = None,
               broadcaster: str | None = None,
               weights: dict[str, float] | None = None) -> SearchResult:
        plan = _with_overrides(analyze(query), year_from, year_to, broadcaster)
        lists: dict[str, list] = {}
        latency: dict[str, int] = {}
        relaxed = False
        graph_match: GraphMatch | None = None
        effective = {**self.list_weights, **(weights or {})}

        def timed(name, fn):
            if effective.get(name, 1.0) <= 0:
                return  # a list weighted 0 is not worth a round trip
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
                timed("vector_synopsis",
                      lambda: self.store.vector_synopsis(vec, filters, self.candidates))
            if use_graph and self.graph is not None and p.text:
                nonlocal graph_match
                t = time.perf_counter()
                try:
                    cands, graph_match = self._graph_list(p.text)
                except Exception as exc:  # graph is optional: never fail the search
                    log.warning("graph candidates failed for %r: %s", p.text, exc)
                    cands, graph_match = [], GraphMatch(mode=f"error:{type(exc).__name__}")
                lists["graph"] = cands
                latency["graph"] = int((time.perf_counter() - t) * 1000)
            if not any(lists.values()) and p.has_constraints and not p.text:
                timed("filter", lambda: self.store.filter_only(filters, self.candidates))

        gather(plan)
        # A "year" that was really part of a title (응답하라 1988) filters everything out:
        # drop the constraints and try once more with the plain text.
        if not any(lists.values()) and plan.has_constraints and plan.text:
            lists.clear()
            plan = _with_overrides(
                analyze(query, extract_constraints=False), year_from, year_to, broadcaster
            )
            relaxed = True
            gather(plan)

        t = time.perf_counter()
        use_rerank = rerank and self.reranker is not None
        fused = rrf(
            lists, k=self.rrf_k, limit=self.rerank_candidates if use_rerank else limit,
            weights=effective,
        )
        docs = self.store.docs([f.doc_id for f in fused])
        latency["fuse"] = int((time.perf_counter() - t) * 1000)

        if use_rerank and fused:
            # Cross-encoder over the fused top-N; RRF evidence stays, rerank is one more list.
            t = time.perf_counter()
            fused = [f for f in fused if f.doc_id in docs]
            scores = self.reranker.score(query, [_rerank_text(docs[f.doc_id]) for f in fused])
            order = sorted(range(len(fused)), key=lambda i: (-scores[i], fused[i].doc_id))
            reranked = []
            for pos, i in enumerate(order[:limit], start=1):
                f = fused[i]
                f.ranks["rerank"] = pos
                f.scores["rerank"] = float(scores[i])
                f.score = float(scores[i])
                reranked.append(f)
            fused = reranked
            lists["rerank"] = fused
            latency["rerank"] = int((time.perf_counter() - t) * 1000)

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
            graph=graph_match,
            reranker=self.reranker.model_id if use_rerank and self.reranker else None,
        )

    def _graph_list(self, text: str):
        # Two round trips: names -> dramas (graph), dramas -> document ids (postgres).
        _, match = graph_candidates(self.graph, text, doc_id_by_drama={}, limit=self.candidates)
        if not match.dramas:
            return [], match
        id_map = self.store.doc_ids_for_dramas([int(d["id"]) for d in match.dramas])
        return graph_candidates(self.graph, text, doc_id_by_drama=id_map, limit=self.candidates)


def _rerank_text(doc: Doc, max_synopsis: int = 600) -> str:
    """What the cross-encoder reads: title, aliases, the metadata/cast body, a slice of plot."""
    parts = [doc.title]
    if doc.aliases:
        parts.append(" / ".join(doc.aliases))
    if doc.body:
        parts.append(doc.body)
    if doc.synopsis:
        parts.append(f"줄거리: {doc.synopsis[:max_synopsis]}")
    return "\n".join(parts)


def _with_overrides(plan: QueryPlan, year_from: int | None, year_to: int | None,
                    broadcaster: str | None) -> QueryPlan:
    """Explicit filters (API params, MCP tool arguments) win over what the text implied."""
    if year_from is None and year_to is None and broadcaster is None:
        return plan
    changes: dict[str, Any] = {}
    if year_from is not None or year_to is not None:
        changes["year_from"] = year_from if year_from is not None else year_to
        changes["year_to"] = year_to if year_to is not None else year_from
    if broadcaster:
        changes["broadcaster"] = broadcaster.lower()
    return replace(plan, signals={**plan.signals, "explicit": ",".join(sorted(changes))}, **changes)


def _strategy(lists: dict[str, list]) -> str:
    lexical = bool(lists.get("fts") or lists.get("fts_any") or lists.get("trigram"))
    vector = bool(lists.get("vector") or lists.get("vector_synopsis"))
    graph = bool(lists.get("graph"))
    if graph and (lexical or vector):
        return "hybrid+graph"
    if graph:
        return "graph"
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
