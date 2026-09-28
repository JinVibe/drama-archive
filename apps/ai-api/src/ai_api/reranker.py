"""(query, document) -> relevance score, for re-ordering fused candidates (RAG_DESIGN §8).

Optional and off by default: a cross-encoder reads every candidate with the
query, which costs far more than the bi-encoder lookup. It is only worth it when
the measured gain on the golden sets justifies the latency (README principle 10).
"""

from __future__ import annotations

import re
from typing import Protocol

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


class Reranker(Protocol):
    model_id: str

    def score(self, query: str, texts: list[str]) -> list[float]: ...


class FakeReranker:
    """Token-overlap ratio: deterministic and cheap, so tests can assert the plumbing
    (candidates re-ordered, evidence recorded) without a model."""

    model_id = "fake/overlap-reranker"

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = {t.casefold() for t in _TOKEN.findall(query)}
        if not q:
            return [0.0 for _ in texts]
        out = []
        for text in texts:
            tokens = {t.casefold() for t in _TOKEN.findall(text)}
            out.append(len(q & tokens) / len(q))
        return out


class CrossEncoderReranker:
    """BAAI/bge-reranker-* via sentence-transformers CrossEncoder (CPU is fine for
    ~30 pairs per query; measure before enabling)."""

    def __init__(self, model_id: str = "BAAI/bge-reranker-v2-m3", max_length: int = 512):
        from sentence_transformers import CrossEncoder  # heavy import, on purpose lazy

        self.model_id = model_id
        self._model = CrossEncoder(model_id, max_length=max_length)

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        scores = self._model.predict([(query, t) for t in texts], convert_to_numpy=True)
        return [float(s) for s in scores]


def build_reranker(kind: str, model_id: str) -> Reranker | None:
    if kind in ("", "none", "off"):
        return None
    if kind == "fake":
        return FakeReranker()
    if kind == "bge":
        return CrossEncoderReranker(model_id=model_id)
    raise ValueError(f"unknown reranker kind {kind!r}")
