"""Candidate generation against search_document. Every query returns a ranked list
of (doc id, score); fusion happens in Python so each retriever stays independent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pgvector.psycopg import register_vector

from ai_api.retrieval.fusion import Candidate

# Optional hard filters shared by every candidate query.
_FILTER = """
  AND (%(year_from)s::int IS NULL
       OR (sd.metadata->>'year')::int BETWEEN %(year_from)s AND %(year_to)s)
  AND (%(broadcaster)s::text IS NULL OR sd.metadata->>'broadcaster_code' = %(broadcaster)s)
"""

FTS_SQL = f"""
SELECT sd.id, ts_rank_cd(sd.fts, q.tsq) AS score
  FROM search_document sd, websearch_to_tsquery('simple', %(text)s) q(tsq)
 WHERE sd.entity_type = 'DRAMA' AND numnode(q.tsq) > 0 AND sd.fts @@ q.tsq
 {_FILTER}
 ORDER BY score DESC, sd.id
 LIMIT %(limit)s
"""

# Any-token match (OR). Catches queries where one word is not in the document
# ("노희경 작가": 작가 never appears, 노희경 does). Ranked below exact AND matches by RRF.
FTS_ANY_SQL = f"""
SELECT sd.id, ts_rank_cd(sd.fts, q.tsq) AS score
  FROM search_document sd, to_tsquery('simple', %(any)s) q(tsq)
 WHERE sd.entity_type = 'DRAMA' AND sd.fts @@ q.tsq
 {_FILTER}
 ORDER BY score DESC, sd.id
 LIMIT %(limit)s
"""

TRIGRAM_SQL = f"""
SELECT sd.id,
       GREATEST(word_similarity(%(text)s, sd.title), word_similarity(%(text)s, sd.aliases)) AS score
  FROM search_document sd
 WHERE sd.entity_type = 'DRAMA'
   AND GREATEST(word_similarity(%(text)s, sd.title), word_similarity(%(text)s, sd.aliases)) >= 0.35
 {_FILTER}
 ORDER BY score DESC, sd.id
 LIMIT %(limit)s
"""

VECTOR_SQL = f"""
SELECT sd.id, 1 - (sd.embedding <=> %(vec)s) AS score
  FROM search_document sd
 WHERE sd.entity_type = 'DRAMA' AND sd.embedding IS NOT NULL
 {_FILTER}
 ORDER BY sd.embedding <=> %(vec)s, sd.id
 LIMIT %(limit)s
"""

# Filter-only fallback: when the query is nothing but constraints ("2016년 tvN").
FILTER_SQL = f"""
SELECT sd.id, 0.0 AS score
  FROM search_document sd
 WHERE sd.entity_type = 'DRAMA'
 {_FILTER}
 ORDER BY (sd.metadata->>'start_date') NULLS LAST, sd.id
 LIMIT %(limit)s
"""

DOC_IDS_FOR_DRAMAS_SQL = """
SELECT entity_id, id FROM search_document WHERE entity_type = 'DRAMA' AND entity_id = ANY(%(ids)s)
"""

DOCS_SQL = """
SELECT id, entity_id, title, aliases, body, metadata
  FROM search_document WHERE id = ANY(%(ids)s)
"""


@dataclass(frozen=True)
class Doc:
    id: int
    drama_id: int
    title: str
    aliases: list[str]
    body: str
    metadata: dict[str, Any]


class SearchStore:
    def __init__(self, pool):
        self.pool = pool

    def _candidates(self, sql: str, params: dict[str, Any]) -> list[Candidate]:
        with self.pool.connection() as conn:
            register_vector(conn)
            rows = conn.execute(sql, params).fetchall()
        return [
            Candidate(doc_id=int(r[0]), rank=i + 1, score=float(r[1])) for i, r in enumerate(rows)
        ]

    def fts(self, text: str, filters: dict[str, Any], limit: int) -> list[Candidate]:
        return self._candidates(FTS_SQL, {"text": text, "limit": limit, **filters})

    def fts_any(self, text: str, filters: dict[str, Any], limit: int) -> list[Candidate]:
        tokens = [t for t in re.split(r"[^0-9A-Za-z\uac00-\ud7a3]+", text.casefold()) if t]
        if not tokens:
            return []
        any_query = " | ".join(f"'{t}'" for t in tokens)
        return self._candidates(FTS_ANY_SQL, {"any": any_query, "limit": limit, **filters})

    def trigram(self, text: str, filters: dict[str, Any], limit: int) -> list[Candidate]:
        return self._candidates(TRIGRAM_SQL, {"text": text, "limit": limit, **filters})

    def vector(self, vec: list[float], filters: dict[str, Any], limit: int) -> list[Candidate]:
        import numpy as np

        return self._candidates(VECTOR_SQL, {"vec": np.array(vec), "limit": limit, **filters})

    def filter_only(self, filters: dict[str, Any], limit: int) -> list[Candidate]:
        return self._candidates(FILTER_SQL, {"limit": limit, **filters})

    def doc_ids_for_dramas(self, drama_ids: list[int]) -> dict[int, int]:
        if not drama_ids:
            return {}
        with self.pool.connection() as conn:
            rows = conn.execute(DOC_IDS_FOR_DRAMAS_SQL, {"ids": drama_ids}).fetchall()
        return {int(r[0]): int(r[1]) for r in rows}

    def docs(self, ids: list[int]) -> dict[int, Doc]:
        if not ids:
            return {}
        with self.pool.connection() as conn:
            rows = conn.execute(DOCS_SQL, {"ids": ids}).fetchall()
        out = {}
        for id_, entity_id, title, aliases, body, metadata in rows:
            meta = metadata if isinstance(metadata, dict) else json.loads(metadata)
            out[int(id_)] = Doc(int(id_), int(entity_id), title,
                                [a for a in aliases.split("\n") if a], body, meta)
        return out
