"""Graph candidate list for hybrid retrieval — docs/RAG_DESIGN.md §5.4.

People named in the query are looked up in the graph. One person -> their works;
two or more -> works they share (co-star / same writer-director team), which is
exactly the multi-hop question lexical and vector retrievers answer badly.
Results become one more ranked list for RRF; nothing here is authoritative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ai_api.graph.queries import GraphClient
from ai_api.retrieval.fusion import Candidate

# Particles that glue to a name in speech: 공유랑, 이동욱이랑, 김혜수와, 이제훈하고
_NAME_SUFFIXES = ("이랑", "랑", "하고", "과", "와", "은", "는", "이", "가", "의", "도")
_TOKEN = re.compile(r"[가-힣]{2,5}")


def name_candidates(text: str) -> list[str]:
    """Hangul tokens (2-5 syllables) plus particle-stripped variants, order preserved, unique."""
    out: list[str] = []
    for tok in _TOKEN.findall(text):
        variants = [tok]
        for suf in _NAME_SUFFIXES:
            if tok.endswith(suf) and len(tok) - len(suf) >= 2:
                variants.append(tok[: -len(suf)])
        for v in variants:
            if v not in out:
                out.append(v)
    return out


@dataclass
class GraphMatch:
    persons: list[dict[str, Any]] = field(default_factory=list)   # matched people
    mode: str = "none"                                            # none | person | shared
    dramas: list[dict[str, Any]] = field(default_factory=list)


def graph_candidates(client: GraphClient, text: str, *, doc_id_by_drama: dict[int, int],
                     limit: int = 50) -> tuple[list[Candidate], GraphMatch]:
    """Returns (RRF candidates keyed by search_document id, evidence)."""
    names = name_candidates(text)
    persons = client.persons_by_name(names) if names else []
    if not persons:
        return [], GraphMatch()

    # Keep one person per distinct name (homonyms: prefer nothing clever, take all ids).
    ids = [int(p["id"]) for p in persons]
    if len({p["name"] for p in persons}) >= 2:
        dramas = client.dramas_shared_by(ids, limit=limit)
        mode = "shared"
        if not dramas:  # they never worked together: fall back to union of their works
            seen: set[int] = set()
            dramas = []
            for pid in ids:
                for d in client.dramas_of_person(pid, limit=limit):
                    if d["id"] not in seen:
                        seen.add(d["id"])
                        dramas.append(d)
            mode = "person"
    else:
        dramas = client.dramas_of_person(ids[0], limit=limit)
        mode = "person"

    candidates = []
    for d in dramas:
        doc_id = doc_id_by_drama.get(int(d["id"]))
        if doc_id is not None:
            candidates.append(Candidate(doc_id=doc_id, rank=len(candidates) + 1, score=1.0))
    return candidates, GraphMatch(persons=persons, mode=mode, dramas=dramas)
