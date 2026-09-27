"""Text -> dense vector. One implementation per model family plus a fake for tests."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic, cheap, dimension-correct. Similar strings do NOT get similar vectors,
    so tests can only assert plumbing (dimension, model id, exact-text matches), not quality."""

    def __init__(self, dim: int = 1024, model_id: str = "fake/hash-embedder"):
        self.dim = dim
        self.model_id = model_id

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
            rng = np.random.default_rng(seed)
            v = rng.standard_normal(self.dim)
            v /= np.linalg.norm(v)
            out.append(v.astype(float).tolist())
        return out


class BgeM3Embedder:
    """BAAI/bge-m3 dense embeddings via sentence-transformers, CPU is fine at this scale.
    Normalized so cosine distance in pgvector is the right metric."""

    def __init__(self, model_id: str = "BAAI/bge-m3", batch_size: int = 16):
        from sentence_transformers import SentenceTransformer  # heavy import, on purpose lazy

        self.model_id = model_id
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_id)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True
        )
        return [v.astype(float).tolist() for v in vectors]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def build_embedder(kind: str, model_id: str, dim: int, batch_size: int) -> Embedder:
    if kind == "fake":
        return FakeEmbedder(dim=dim, model_id=f"fake/{model_id}")
    if kind == "bge":
        return BgeM3Embedder(model_id=model_id, batch_size=batch_size)
    raise ValueError(f"unknown embedder kind {kind!r}")
