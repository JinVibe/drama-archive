"""PostgreSQL implementation of `matching.Repo`. Only PUBLISHED canonical rows are candidates."""

from __future__ import annotations

from dramamemory_data.entity_resolution.matching import (
    DramaCandidate,
    PersonCandidate,
    SongCandidate,
)


class PostgresRepo:
    def __init__(self, cur):
        self.cur = cur

    def mapped_canonical_id(
        self, source_id: int, canonical_type: str, external_ref: str
    ) -> int | None:
        self.cur.execute(
            """
            SELECT m.canonical_id
            FROM source_entity_map m
            JOIN source_record sr ON sr.id = m.source_record_id
            WHERE sr.source_id = %s AND m.canonical_type = %s AND m.external_ref = %s
              AND m.decision IN ('AUTO_MERGE', 'CREATE_NEW')
            ORDER BY m.created_at DESC
            LIMIT 1
            """,
            (source_id, canonical_type, external_ref),
        )
        row = self.cur.fetchone()
        return int(row[0]) if row else None

    def dramas_by_title(self, title_normalized: str) -> list[DramaCandidate]:
        self.cur.execute(
            """
            SELECT d.id, d.title_normalized, b.code, EXTRACT(YEAR FROM d.start_date)::int
            FROM drama d
            LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
            WHERE d.status = 'PUBLISHED'
              AND (d.title_normalized = %s
                   OR EXISTS (SELECT 1 FROM drama_alias a
                              WHERE a.drama_id = d.id AND a.alias_normalized = %s))
            ORDER BY d.id
            """,
            (title_normalized, title_normalized),
        )
        return [DramaCandidate(int(r[0]), r[1], r[2], r[3]) for r in self.cur.fetchall()]

    def persons_by_name(self, name_normalized: str) -> list[PersonCandidate]:
        self.cur.execute(
            """
            SELECT p.id, p.name_normalized, p.birth_date,
                   COALESCE(array_agg(c.drama_id) FILTER (WHERE c.drama_id IS NOT NULL), '{}')
            FROM person p
            LEFT JOIN credit c ON c.person_id = p.id
            WHERE p.status = 'PUBLISHED' AND p.name_normalized = %s
            GROUP BY p.id
            ORDER BY p.id
            """,
            (name_normalized,),
        )
        return [
            PersonCandidate(int(r[0]), r[1], r[2], frozenset(int(x) for x in r[3]))
            for r in self.cur.fetchall()
        ]

    def songs_by_title(self, title_normalized: str) -> list[SongCandidate]:
        self.cur.execute(
            """
            SELECT s.id, s.title_normalized,
                   COALESCE((SELECT array_agg(a.name_normalized) FROM song_artist sa
                             JOIN artist a ON a.id = sa.artist_id WHERE sa.song_id = s.id), '{}'),
                   COALESCE((SELECT array_agg(o.drama_id) FROM drama_ost o
                             WHERE o.song_id = s.id), '{}')
            FROM song s
            WHERE s.title_normalized = %s
            ORDER BY s.id
            """,
            (title_normalized,),
        )
        return [
            SongCandidate(int(r[0]), r[1], frozenset(r[2]), frozenset(int(x) for x in r[3]))
            for r in self.cur.fetchall()
        ]

    def artist_by_name(self, name_normalized: str) -> int | None:
        self.cur.execute("SELECT id FROM artist WHERE name_normalized = %s", (name_normalized,))
        row = self.cur.fetchone()
        return int(row[0]) if row else None
