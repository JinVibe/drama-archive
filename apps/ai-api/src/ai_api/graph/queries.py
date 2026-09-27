"""Parameterized Cypher + a small client. Results are plain dicts keyed by canonical ids."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

MAX_LIMIT = 50
TIMEOUT_SECONDS = 3.0


class GraphRunner(Protocol):
    """What the client needs from a driver: run one read query, get dict rows."""

    def rows(self, cypher: str, **params: Any) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------- cypher
PERSONS_BY_NAME = """
MATCH (p:Person) WHERE p.name IN $names
RETURN p.canonical_id AS id, p.name AS name, p.slug AS slug
"""

DRAMAS_OF_PERSON = """
MATCH (p:Person {canonical_id: $id})-[r:ACTED_IN|DIRECTED|WROTE|PRODUCED]->(d:Drama)
RETURN DISTINCT d.canonical_id AS id, d.slug AS slug, d.title AS title, d.start_year AS year,
       d.start_date AS start_date, type(r) AS credit
ORDER BY start_date DESC
LIMIT $limit
"""

# Dramas that every one of the given people is credited in (co-star / same team).
DRAMAS_SHARED_BY_PERSONS = """
MATCH (p:Person)-[:ACTED_IN|DIRECTED|WROTE|PRODUCED]->(d:Drama)
WHERE p.canonical_id IN $ids
WITH d, count(DISTINCT p) AS shared
WHERE shared = size($ids)
RETURN d.canonical_id AS id, d.slug AS slug, d.title AS title, d.start_year AS year
ORDER BY d.start_date DESC
LIMIT $limit
"""

COLLABORATORS = """
MATCH (p:Person {canonical_id: $id})-[:ACTED_IN]->(d:Drama)<-[:ACTED_IN]-(co:Person)
WHERE co.canonical_id <> p.canonical_id
WITH co,
     collect(DISTINCT {id: d.canonical_id, slug: d.slug, title: d.title}) AS dramas
RETURN co.canonical_id AS id, co.name AS name, co.slug AS slug, size(dramas) AS works, dramas
ORDER BY works DESC, co.name
LIMIT $limit
"""

# Other dramas reachable through this drama's cast/crew, with who connects them.
RELATED_BY_PEOPLE = """
MATCH (d:Drama {canonical_id: $id})<-[:ACTED_IN|DIRECTED|WROTE]-(p:Person)
      -[r:ACTED_IN|DIRECTED|WROTE]->(other:Drama)
WHERE other.canonical_id <> d.canonical_id
WITH other, collect(DISTINCT {id: p.canonical_id, name: p.name, slug: p.slug, credit: type(r)}) AS via
RETURN other.canonical_id AS id, other.slug AS slug, other.title AS title,
       other.start_year AS year, via, size(via) AS strength
ORDER BY strength DESC, other.start_date DESC
LIMIT $limit
"""

# Other dramas whose OST artists also sang for this drama.
RELATED_BY_OST_ARTISTS = """
MATCH (d:Drama {canonical_id: $id})-[:HAS_OST]->(:Song)<-[:PERFORMED]-(a:Artist)
      -[:PERFORMED]->(s:Song)<-[:HAS_OST]-(other:Drama)
WHERE other.canonical_id <> d.canonical_id
WITH other, collect(DISTINCT {id: a.canonical_id, name: a.name}) AS artists
RETURN other.canonical_id AS id, other.slug AS slug, other.title AS title,
       other.start_year AS year, artists
ORDER BY size(artists) DESC, other.start_date DESC
LIMIT $limit
"""


# ---------------------------------------------------------------------------- client
@dataclass
class GraphClient:
    runner: GraphRunner
    default_limit: int = 20

    def _limit(self, limit: int | None) -> int:
        return max(1, min(limit or self.default_limit, MAX_LIMIT))

    def persons_by_name(self, names: list[str]) -> list[dict[str, Any]]:
        if not names:
            return []
        return self.runner.rows(PERSONS_BY_NAME, names=names)

    def dramas_of_person(self, person_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        return self.runner.rows(DRAMAS_OF_PERSON, id=person_id, limit=self._limit(limit))

    def dramas_shared_by(
        self, person_ids: list[int], limit: int | None = None
    ) -> list[dict[str, Any]]:
        if len(person_ids) < 2:
            return []
        return self.runner.rows(DRAMAS_SHARED_BY_PERSONS, ids=person_ids, limit=self._limit(limit))

    def collaborators(self, person_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        return self.runner.rows(COLLABORATORS, id=person_id, limit=self._limit(limit))

    def related(self, drama_id: int, limit: int | None = None) -> dict[str, list[dict[str, Any]]]:
        lim = self._limit(limit)
        return {
            "by_people": self.runner.rows(RELATED_BY_PEOPLE, id=drama_id, limit=lim),
            "by_ost_artists": self.runner.rows(RELATED_BY_OST_ARTISTS, id=drama_id, limit=lim),
        }


@dataclass
class Neo4jRunner:
    """Real runner. Read transactions with a hard timeout (GRAPH_MODEL §14)."""

    uri: str
    user: str
    password: str
    _driver: Any = field(default=None, repr=False)

    def open(self) -> None:
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self._driver.verify_connectivity()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()

    def rows(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        from neo4j import Query

        with self._driver.session(default_access_mode="READ") as session:
            result = session.run(Query(cypher, timeout=TIMEOUT_SECONDS), **params)
            return [r.data() for r in result]
