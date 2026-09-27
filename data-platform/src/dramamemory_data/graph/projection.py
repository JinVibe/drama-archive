"""Per-drama graph projection — docs/GRAPH_MODEL.md §3-§7.

Identity rule: every node carries the PostgreSQL canonical id; Neo4j internal ids
are never exposed. A drama is projected as one aggregate: its node, its
broadcaster/genre edges, cast/crew edges, OST songs and their artists. Rebuilding
an aggregate deletes the drama's edges first, so source corrections never leave
stale relationships (§7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# schema (idempotent)
# ---------------------------------------------------------------------------
SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT drama_canonical_id IF NOT EXISTS FOR (d:Drama) REQUIRE d.canonical_id IS UNIQUE",
    "CREATE CONSTRAINT person_canonical_id IF NOT EXISTS FOR (p:Person) REQUIRE p.canonical_id IS UNIQUE",
    "CREATE CONSTRAINT song_canonical_id IF NOT EXISTS FOR (s:Song) REQUIRE s.canonical_id IS UNIQUE",
    "CREATE CONSTRAINT artist_canonical_id IF NOT EXISTS FOR (a:Artist) REQUIRE a.canonical_id IS UNIQUE",
    "CREATE CONSTRAINT broadcaster_code IF NOT EXISTS FOR (b:Broadcaster) REQUIRE b.code IS UNIQUE",
    "CREATE CONSTRAINT genre_code IF NOT EXISTS FOR (g:Genre) REQUIRE g.code IS UNIQUE",
    "CREATE INDEX drama_start_year IF NOT EXISTS FOR (d:Drama) ON (d.start_year)",
    "CREATE INDEX drama_slug IF NOT EXISTS FOR (d:Drama) ON (d.slug)",
    "CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name)",
    "CREATE INDEX person_slug IF NOT EXISTS FOR (p:Person) ON (p.slug)",
    "CREATE INDEX artist_name IF NOT EXISTS FOR (a:Artist) ON (a.name)",
]

# ---------------------------------------------------------------------------
# what one aggregate looks like
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PersonRef:
    id: int
    slug: str
    name: str
    name_en: str | None
    birth_date: str | None


@dataclass(frozen=True)
class CreditRef:
    person: PersonRef
    credit_type: str            # ACTOR / DIRECTOR / WRITER / PRODUCER
    character_name: str | None
    billing_order: int | None
    is_main_cast: bool


@dataclass(frozen=True)
class ArtistRef:
    id: int
    name: str
    role: str
    sort_order: int | None


@dataclass(frozen=True)
class SongRef:
    id: int
    title: str
    release_date: str | None
    part_no: int | None
    track_no: int | None
    artists: list[ArtistRef] = field(default_factory=list)


@dataclass(frozen=True)
class DramaAggregate:
    id: int
    slug: str
    title: str
    title_en: str | None
    start_date: str | None
    end_date: str | None
    episode_count: int | None
    canonical_version: int
    broadcaster: tuple[str, str] | None          # (code, name)
    genres: list[tuple[str, str]] = field(default_factory=list)   # (code, name)
    credits: list[CreditRef] = field(default_factory=list)
    songs: list[SongRef] = field(default_factory=list)

    @property
    def start_year(self) -> int | None:
        return int(self.start_date[:4]) if self.start_date else None


# ---------------------------------------------------------------------------
# SQL to load aggregates
# ---------------------------------------------------------------------------
SELECT_PUBLISHED_VERSIONS = "SELECT id, canonical_version FROM drama WHERE status = 'PUBLISHED'"

SELECT_DRAMA = """
SELECT d.id, d.slug, d.title_ko, d.title_en, d.start_date::text, d.end_date::text,
       d.episode_count, d.canonical_version, b.code, b.name_ko,
       COALESCE((SELECT json_agg(json_build_array(g.code, g.name_ko) ORDER BY g.code)
                   FROM drama_genre dg JOIN genre g ON g.id = dg.genre_id WHERE dg.drama_id = d.id), '[]'),
       COALESCE((SELECT json_agg(json_build_array(p.id, p.slug, p.name_ko, p.name_en, p.birth_date::text,
                                                  c.credit_type, c.character_name, c.billing_order, c.is_main_cast)
                                 ORDER BY c.credit_type, c.billing_order NULLS LAST, p.name_ko)
                   FROM credit c JOIN person p ON p.id = c.person_id
                  WHERE c.drama_id = d.id AND p.status = 'PUBLISHED'), '[]'),
       COALESCE((SELECT json_agg(json_build_array(s.id, s.title, s.release_date::text, o.part_no, o.track_no,
                       COALESCE((SELECT json_agg(json_build_array(a.id, a.name, sa.role, sa.sort_order)
                                                 ORDER BY sa.sort_order NULLS LAST)
                                   FROM song_artist sa JOIN artist a ON a.id = sa.artist_id
                                  WHERE sa.song_id = s.id), '[]'))
                                 ORDER BY o.part_no NULLS LAST, o.track_no NULLS LAST)
                   FROM drama_ost o JOIN song s ON s.id = o.song_id WHERE o.drama_id = d.id), '[]')
  FROM drama d LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
 WHERE d.id = %s
"""


def row_to_aggregate(row: tuple) -> DramaAggregate:
    (id_, slug, title, title_en, start, end, episodes, version, bc_code, bc_name,
     genres, credits, songs) = row
    return DramaAggregate(
        id=int(id_), slug=slug, title=title, title_en=title_en, start_date=start, end_date=end,
        episode_count=episodes, canonical_version=int(version),
        broadcaster=(bc_code, bc_name) if bc_code else None,
        genres=[(c, n) for c, n in genres],
        credits=[
            CreditRef(PersonRef(int(pid), pslug, pname, pname_en, birth), ctype, char, order, bool(main))
            for pid, pslug, pname, pname_en, birth, ctype, char, order, main in credits
        ],
        songs=[
            SongRef(int(sid), stitle, srel, part, track,
                    [ArtistRef(int(aid), aname, role, so) for aid, aname, role, so in artists])
            for sid, stitle, srel, part, track, artists in songs
        ],
    )


# ---------------------------------------------------------------------------
# Cypher for one aggregate (executed in one transaction)
# ---------------------------------------------------------------------------
CREDIT_EDGE = {"ACTOR": "ACTED_IN", "DIRECTOR": "DIRECTED", "WRITER": "WROTE", "PRODUCER": "PRODUCED"}


def aggregate_statements(d: DramaAggregate) -> list[tuple[str, dict[str, Any]]]:
    """Ordered (cypher, params). Node MERGEs are keyed on canonical ids; all edges of the
    drama (and PERFORMED edges of its songs) are dropped and recreated."""
    stmts: list[tuple[str, dict[str, Any]]] = []

    stmts.append((
        """
        MERGE (d:Drama {canonical_id: $id})
        SET d.slug = $slug, d.title = $title, d.title_en = $title_en,
            d.start_date = $start_date, d.end_date = $end_date, d.start_year = $start_year,
            d.episode_count = $episode_count, d.canonical_version = $version
        WITH d
        OPTIONAL MATCH (d)-[r]-()
        DELETE r
        """,
        {"id": d.id, "slug": d.slug, "title": d.title, "title_en": d.title_en,
         "start_date": d.start_date, "end_date": d.end_date, "start_year": d.start_year,
         "episode_count": d.episode_count, "version": d.canonical_version},
    ))

    if d.broadcaster:
        code, name = d.broadcaster
        stmts.append((
            """
            MATCH (d:Drama {canonical_id: $id})
            MERGE (b:Broadcaster {code: $code}) SET b.name = $name
            MERGE (d)-[:AIRED_BY]->(b)
            """,
            {"id": d.id, "code": code, "name": name},
        ))

    for code, name in d.genres:
        stmts.append((
            """
            MATCH (d:Drama {canonical_id: $id})
            MERGE (g:Genre {code: $code}) SET g.name = $name
            MERGE (d)-[:HAS_GENRE]->(g)
            """,
            {"id": d.id, "code": code, "name": name},
        ))

    for c in d.credits:
        edge = CREDIT_EDGE.get(c.credit_type, "CREDITED_IN")
        stmts.append((
            f"""
            MATCH (d:Drama {{canonical_id: $id}})
            MERGE (p:Person {{canonical_id: $pid}})
            SET p.slug = $slug, p.name = $name, p.name_en = $name_en, p.birth_date = $birth_date
            MERGE (p)-[r:{edge}]->(d)
            SET r.character_name = $character, r.billing_order = $order, r.main_cast = $main
            """,
            {"id": d.id, "pid": c.person.id, "slug": c.person.slug, "name": c.person.name,
             "name_en": c.person.name_en, "birth_date": c.person.birth_date,
             "character": c.character_name, "order": c.billing_order, "main": c.is_main_cast},
        ))

    for s in d.songs:
        stmts.append((
            """
            MATCH (d:Drama {canonical_id: $id})
            MERGE (s:Song {canonical_id: $sid})
            SET s.title = $title, s.release_date = $release_date
            MERGE (d)-[r:HAS_OST]->(s)
            SET r.part_no = $part_no, r.track_no = $track_no
            WITH s
            OPTIONAL MATCH (:Artist)-[pr:PERFORMED]->(s)
            DELETE pr
            """,
            {"id": d.id, "sid": s.id, "title": s.title, "release_date": s.release_date,
             "part_no": s.part_no, "track_no": s.track_no},
        ))
        for a in s.artists:
            stmts.append((
                """
                MATCH (s:Song {canonical_id: $sid})
                MERGE (a:Artist {canonical_id: $aid}) SET a.name = $name
                MERGE (a)-[r:PERFORMED]->(s)
                SET r.role = $role, r.sort_order = $sort_order
                """,
                {"sid": s.id, "aid": a.id, "name": a.name, "role": a.role, "sort_order": a.sort_order},
            ))
    return stmts


# ---------------------------------------------------------------------------
# reconciliation
# ---------------------------------------------------------------------------
GRAPH_VERSIONS = "MATCH (d:Drama) RETURN d.canonical_id AS id, d.canonical_version AS version"

REMOVE_UNPUBLISHED = """
MATCH (d:Drama) WHERE NOT d.canonical_id IN $published
DETACH DELETE d
RETURN count(*) AS removed
"""

REMOVE_ORPHANS = """
MATCH (n) WHERE NOT n:Drama AND NOT (n)--()
DELETE n
RETURN count(*) AS removed
"""


def dramas_to_rebuild(pg_versions: dict[int, int], graph_versions: dict[int, int]) -> list[int]:
    """Dramas missing from the graph or projected from an older canonical_version."""
    return sorted(
        did for did, ver in pg_versions.items()
        if did not in graph_versions or graph_versions[did] < ver
    )


# ---------------------------------------------------------------------------
# integrity (§15)
# ---------------------------------------------------------------------------
INTEGRITY_QUERIES = {
    "drama_count": "MATCH (d:Drama) RETURN count(d) AS n",
    "person_count": "MATCH (p:Person) RETURN count(p) AS n",
    "song_count": "MATCH (s:Song) RETURN count(s) AS n",
    "artist_count": "MATCH (a:Artist) RETURN count(a) AS n",
    "acted_in": "MATCH ()-[r:ACTED_IN]->() RETURN count(r) AS n",
    "has_ost": "MATCH ()-[r:HAS_OST]->() RETURN count(r) AS n",
    "performed": "MATCH ()-[r:PERFORMED]->() RETURN count(r) AS n",
    "orphans": "MATCH (n) WHERE NOT n:Drama AND NOT (n)--() RETURN count(n) AS n",
    "dramas_without_broadcaster": "MATCH (d:Drama) WHERE NOT (d)-[:AIRED_BY]->() RETURN count(d) AS n",
    "max_person_degree": "MATCH (p:Person)-[r:ACTED_IN]->() WITH p, count(r) AS n "
                         "RETURN n ORDER BY n DESC LIMIT 1",
}


class IntegrityError(RuntimeError):
    pass


def check_integrity(stats: dict[str, int], *, published_count: int, max_degree: int = 500) -> list[str]:
    """Returns warnings; raises IntegrityError on conditions that must block the asset."""
    if stats["drama_count"] != published_count:
        raise IntegrityError(
            f"graph has {stats['drama_count']} dramas, PostgreSQL has {published_count} published"
        )
    if stats["orphans"] > 0:
        raise IntegrityError(f"{stats['orphans']} orphan non-drama nodes after reconciliation")
    warnings = []
    if stats["dramas_without_broadcaster"] > 0:
        warnings.append(f"{stats['dramas_without_broadcaster']} dramas without AIRED_BY")
    if stats.get("max_person_degree", 0) > max_degree:
        warnings.append(f"person degree spike: {stats['max_person_degree']} ACTED_IN edges")
    return warnings
