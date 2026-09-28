"""Reciprocal Rank Fusion — README principle 6: never add raw scores across retrievers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Candidate:
    doc_id: int
    rank: int          # 1-based rank inside its own list
    score: float       # the retriever's own score, kept for evidence only


@dataclass
class Fused:
    doc_id: int
    score: float
    ranks: dict[str, int] = field(default_factory=dict)      # list name -> rank
    scores: dict[str, float] = field(default_factory=dict)   # list name -> raw score


def rrf(
    lists: dict[str, list[Candidate]],
    k: int = 60,
    limit: int | None = None,
    weights: dict[str, float] | None = None,
) -> list[Fused]:
    """Fuse named ranked lists. Ties break on lower doc_id for determinism.
    `weights` scales a list's contribution (default 1.0 each) — set from measurement,
    not by hand (README principle 10)."""
    fused: dict[int, Fused] = {}
    for name, candidates in lists.items():
        w = (weights or {}).get(name, 1.0)
        for c in candidates:
            f = fused.setdefault(c.doc_id, Fused(doc_id=c.doc_id, score=0.0))
            f.score += w / (k + c.rank)
            f.ranks[name] = c.rank
            f.scores[name] = c.score
    ordered = sorted(fused.values(), key=lambda f: (-f.score, f.doc_id))
    return ordered[:limit] if limit else ordered
