"""Render one search document per published drama — docs/AIRFLOW_DAGS.md §11.

The document is what lexical search (now) and embeddings (DM-601) see, so it is
deliberately plain text in the words a person would type: Korean genre names,
cast and character names, OST titles and artists. No canonical IDs in the text.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

GENRE_LABEL = {
    "romance": "로맨스", "comedy": "코미디", "melodrama": "멜로", "fantasy": "판타지",
    "thriller": "스릴러", "mystery": "미스터리", "crime": "범죄", "action": "액션",
    "medical": "의학", "legal": "법정", "historical": "사극", "family": "가족",
    "youth": "청춘", "office": "오피스", "sf": "SF", "horror": "공포", "daily": "일일",
}

DOCUMENT_VERSION = 2  # 2: synopsis is its own field (V14)


@dataclass(frozen=True)
class DramaSource:
    """Everything the renderer needs, as loaded by SELECT_DRAMAS."""

    id: int
    slug: str
    title_ko: str
    title_en: str | None
    aliases: list[str]
    broadcaster_code: str | None
    broadcaster_name: str | None
    start_date: str | None
    end_date: str | None
    episode_count: int | None
    synopsis: str | None
    genres: list[str]
    cast: list[tuple[str, str | None]] = field(default_factory=list)   # (name, character)
    crew: list[tuple[str, str]] = field(default_factory=list)          # (name, credit_type)
    osts: list[tuple[str, list[str]]] = field(default_factory=list)    # (title, artists)
    canonical_version: int = 1


@dataclass(frozen=True)
class SearchDocument:
    entity_type: str
    entity_id: int
    title: str
    aliases: str
    body: str
    synopsis: str
    metadata: dict[str, Any]
    content_hash: str


def _year(iso: str | None) -> int | None:
    return int(iso[:4]) if iso else None


def render_drama(d: DramaSource) -> SearchDocument:
    year = _year(d.start_date)
    aliases = [a for a in [d.title_en, *d.aliases] if a]
    lines: list[str] = []
    if d.broadcaster_name:
        lines.append(f"방송사: {d.broadcaster_name}")
    if year:
        lines.append(f"연도: {year}년")
    if d.genres:
        lines.append("장르: " + ", ".join(GENRE_LABEL.get(g, g) for g in d.genres))
    if d.cast:
        lines.append("출연: " + ", ".join(f"{n} ({c} 역)" if c else n for n, c in d.cast))
    for name, kind in d.crew:
        label = {"DIRECTOR": "연출", "WRITER": "극본", "PRODUCER": "제작"}.get(kind, kind)
        lines.append(f"{label}: {name}")
    if d.osts:
        lines.append("OST: " + ", ".join(f"{t} - {', '.join(a)}" if a else t for t, a in d.osts))
    body = "\n".join(lines)
    # The plot stays out of body: it is weighted C in fts and embedded separately (V14).
    synopsis = (d.synopsis or "").strip()

    metadata = {
        "slug": d.slug,
        "title_en": d.title_en,
        "broadcaster_code": d.broadcaster_code,
        "broadcaster_name": d.broadcaster_name,
        "year": year,
        "start_date": d.start_date,
        "end_date": d.end_date,
        "episode_count": d.episode_count,
        "genres": d.genres,
        "cast": [n for n, _ in d.cast],
        "canonical_version": d.canonical_version,
        "document_version": DOCUMENT_VERSION,
    }
    alias_text = "\n".join(aliases)
    # canonical_version is bookkeeping, not content: a re-publish that changes nothing the
    # reader sees must not rewrite (and re-embed) every document.
    hashed = {k: v for k, v in metadata.items() if k != "canonical_version"}
    digest = hashlib.sha256(
        json.dumps(
            [d.title_ko, alias_text, body, synopsis, hashed], ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    return SearchDocument(
        "DRAMA", d.id, d.title_ko, alias_text, body, synopsis, metadata, digest
    )


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# Published dramas whose canonical row changed after their document was written (or have none).
SELECT_DRAMAS = """
SELECT d.id, d.slug, d.title_ko, d.title_en,
       COALESCE((SELECT array_agg(a.alias ORDER BY a.alias)
                   FROM drama_alias a WHERE a.drama_id = d.id), '{}'),
       b.code, b.name_ko,
       d.start_date::text, d.end_date::text, d.episode_count, d.synopsis,
       COALESCE((SELECT array_agg(g.code ORDER BY g.code)
                   FROM drama_genre dg JOIN genre g ON g.id = dg.genre_id
                  WHERE dg.drama_id = d.id), '{}'),
       COALESCE((SELECT json_agg(json_build_array(p.name_ko, c.character_name)
                                 ORDER BY c.billing_order NULLS LAST, p.name_ko)
                   FROM credit c JOIN person p ON p.id = c.person_id
                  WHERE c.drama_id = d.id AND c.credit_type = 'ACTOR'
                    AND p.status = 'PUBLISHED'), '[]'),
       COALESCE((SELECT json_agg(json_build_array(p.name_ko, c.credit_type)
                                 ORDER BY c.credit_type, p.name_ko)
                   FROM credit c JOIN person p ON p.id = c.person_id
                  WHERE c.drama_id = d.id AND c.credit_type <> 'ACTOR'
                    AND p.status = 'PUBLISHED'), '[]'),
       COALESCE((SELECT json_agg(json_build_array(s.title,
                   COALESCE((SELECT array_agg(a.name ORDER BY sa.sort_order)
                               FROM song_artist sa JOIN artist a ON a.id = sa.artist_id
                              WHERE sa.song_id = s.id), '{}'))
                             ORDER BY o.part_no NULLS LAST, o.track_no NULLS LAST)
                   FROM drama_ost o JOIN song s ON s.id = o.song_id
                  WHERE o.drama_id = d.id), '[]'),
       d.canonical_version
  FROM drama d
  LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
  LEFT JOIN search_document sd ON sd.entity_type = 'DRAMA' AND sd.entity_id = d.id
 WHERE d.status = 'PUBLISHED'
   AND (sd.id IS NULL OR sd.updated_at < d.updated_at
        OR (sd.metadata->>'document_version')::int <> %s)
 ORDER BY d.id
"""

UPSERT_DOCUMENT = """
INSERT INTO search_document (entity_type, entity_id, title, aliases, body, synopsis, metadata,
                             content_hash)
VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
ON CONFLICT (entity_type, entity_id) DO UPDATE SET
    title = EXCLUDED.title,
    aliases = EXCLUDED.aliases,
    body = EXCLUDED.body,
    synopsis = EXCLUDED.synopsis,
    metadata = EXCLUDED.metadata,
    content_hash = EXCLUDED.content_hash,
    document_version = search_document.document_version + 1,
    updated_at = now()
WHERE search_document.content_hash <> EXCLUDED.content_hash
RETURNING id
"""

# Documents whose drama is no longer published.
DELETE_STALE = """
DELETE FROM search_document sd
 WHERE sd.entity_type = 'DRAMA'
   AND NOT EXISTS (SELECT 1 FROM drama d WHERE d.id = sd.entity_id AND d.status = 'PUBLISHED')
"""


def row_to_source(row: tuple) -> DramaSource:
    (id_, slug, title_ko, title_en, aliases, bc_code, bc_name, start, end, episodes, synopsis,
     genres, cast, crew, osts, version) = row
    return DramaSource(
        id=int(id_), slug=slug, title_ko=title_ko, title_en=title_en, aliases=list(aliases),
        broadcaster_code=bc_code, broadcaster_name=bc_name, start_date=start, end_date=end,
        episode_count=episodes, synopsis=synopsis, genres=list(genres),
        cast=[(n, c) for n, c in cast], crew=[(n, k) for n, k in crew],
        osts=[(t, list(a)) for t, a in osts], canonical_version=int(version),
    )


def upsert_document(cur, doc: SearchDocument) -> bool:
    """Returns True when a row was written (new or changed content)."""
    cur.execute(
        UPSERT_DOCUMENT,
        (doc.entity_type, doc.entity_id, doc.title, doc.aliases, doc.body, doc.synopsis,
         json.dumps(doc.metadata, ensure_ascii=False), doc.content_hash),
    )
    return cur.fetchone() is not None
