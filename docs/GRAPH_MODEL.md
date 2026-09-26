# Knowledge Graph / Neo4j Model

## 1. 목표

드라마의 핵심 데이터는 단순 문서 집합이 아니라 관계망이다.

```text
배우 ↔ 작품 ↔ OST ↔ 가수 ↔ 다른 작품
           ↕
        방송사 / 연도 / 장르
```

Neo4j는 이 관계를 빠르게 탐색하기 위한 derived graph read model로 사용한다.

---

# 2. Identity Rule

모든 노드는 PostgreSQL canonical ID를 가진다.

```text
(:Drama {canonical_id: 123})
(:Person {canonical_id: 456})
```

Neo4j internal ID는 API에 노출하지 않는다.

---

# 3. Node Labels

## Drama

```text
canonical_id
slug
title
start_date
end_date
episode_count
canonical_version
```

## Person

```text
canonical_id
name
birth_date
canonical_version
```

## Character

캐릭터가 실제 기능에 필요해질 때만 canonical entity로 승격한다.

```text
name
drama_id
```

## Song

```text
canonical_id
title
release_date
```

## Artist

```text
canonical_id
name
```

## Broadcaster

```text
canonical_id
code
name
```

## Genre

```text
canonical_id
code
name
```

## Platform

```text
code
name
```

## Year

optional convenience node.

대부분은 `Drama.start_year` property로 충분하므로 query UX가 실제로 좋아지는지 확인 후 유지한다.

## Concept

GraphRAG/curation derived.

```text
concept_id
label
source
confidence
index_version
```

---

# 4. Edges

```text
(Person)-[:ACTED_IN]->(Drama)
(Person)-[:DIRECTED]->(Drama)
(Person)-[:WROTE]->(Drama)

(Person)-[:PLAYED {character_name}]->(Drama)

(Drama)-[:HAS_OST {part_no}]->(Song)
(Artist)-[:PERFORMED]->(Song)

(Drama)-[:AIRED_BY]->(Broadcaster)
(Drama)-[:HAS_GENRE]->(Genre)
(Drama)-[:AVAILABLE_ON {status, last_verified_at}]->(Platform)

(Drama)-[:HAS_CONCEPT {confidence}]->(Concept)
(Drama)-[:THEMATICALLY_RELATED {score, version}]->(Drama)
```

---

# 5. Constraints / Indexes

예시:

```cypher
CREATE CONSTRAINT drama_canonical_id IF NOT EXISTS
FOR (d:Drama) REQUIRE d.canonical_id IS UNIQUE;

CREATE CONSTRAINT person_canonical_id IF NOT EXISTS
FOR (p:Person) REQUIRE p.canonical_id IS UNIQUE;

CREATE INDEX drama_start_date IF NOT EXISTS
FOR (d:Drama) ON (d.start_date);
```

---

# 6. Materialization

PostgreSQL:

```text
drama
credit
drama_ost
song_artist
drama_genre
streaming_link
```

→ Airflow transformation → Neo4j.

### Upsert pattern

```cypher
MERGE (d:Drama {canonical_id: $id})
SET d.title = $title,
    d.slug = $slug,
    d.canonical_version = $version;
```

edge:

```cypher
MATCH (p:Person {canonical_id: $personId})
MATCH (d:Drama {canonical_id: $dramaId})
MERGE (p)-[r:ACTED_IN]->(d)
SET r.billing_order = $billingOrder;
```

---

# 7. Stale Edge Removal

upsert만 하면 source correction 시 stale relationship이 남는다.

방법:

- projection version
- per-aggregate replace
- reconciliation job

예:

```text
Drama 123의 canonical version 증가
→ Drama 123 주변 canonical edges 재생성
→ 기존 edge 중 새 snapshot에 없는 edge 제거
```

---

# 8. Query Examples

## 배우 출연작

```cypher
MATCH (p:Person {canonical_id: $personId})-[:ACTED_IN]->(d:Drama)
RETURN d.canonical_id, d.title, d.start_date
ORDER BY d.start_date;
```

## 두 배우가 함께 출연한 작품

```cypher
MATCH (a:Person {canonical_id: $a})-[:ACTED_IN]->(d:Drama)<-[:ACTED_IN]-(b:Person {canonical_id: $b})
RETURN d;
```

## 작품 → OST → 가수

```cypher
MATCH (d:Drama {canonical_id: $dramaId})-[:HAS_OST]->(s:Song)<-[:PERFORMED]-(a:Artist)
RETURN s, collect(a);
```

## 작품 OST 가수가 참여한 다른 작품

```cypher
MATCH (d:Drama {canonical_id: $id})-[:HAS_OST]->(:Song)<-[:PERFORMED]-(a:Artist)
MATCH (a)-[:PERFORMED]->(:Song)<-[:HAS_OST]-(other:Drama)
WHERE other.canonical_id <> d.canonical_id
RETURN DISTINCT other, a;
```

## actor collaboration

```cypher
MATCH (p:Person {canonical_id: $id})-[:ACTED_IN]->(d:Drama)<-[:ACTED_IN]-(co:Person)
WHERE co.canonical_id <> p.canonical_id
RETURN co, count(DISTINCT d) AS works
ORDER BY works DESC;
```

---

# 9. Graph Features

## Actor Collaboration Score

```text
shared_drama_count
recency_weight
main_cast_overlap
```

UI에서 “관계 강도”를 보여주더라도 의미를 명확히 한다. 인간 관계의 친밀도를 추정하지 않는다.

## Drama Similarity

구조 feature:

```text
genre overlap
cast overlap
year proximity
broadcaster
OST artist overlap
```

semantic feature:

```text
embedding similarity
concept overlap
```

---

# 10. GraphRAG Integration

GraphRAG가 추출한 entity를 canonical node에 무조건 merge하지 않는다.

### Linking layer

```text
GraphRAG extracted entity
      ↓ resolution
canonical entity?
  yes → link
  no  → derived Concept/Entity namespace
```

derived relationship metadata:

```text
source_document_id
graphrag_index_version
confidence
created_at
```

---

# 11. Community Detection

Canonical graph에도 별도 community algorithm을 실험할 수 있다.

예:

- actor collaboration community
- OST artist/drama community
- genre-era cluster

GraphRAG의 community는 **비정형 corpus에서 생성한 graph**의 community와 구별해 기록한다.

---

# 12. Vector in Neo4j?

Neo4j 자체도 vector index를 지원하지만 초기 canonical semantic search는 pgvector를 유지한다.

이유:

- system complexity 감소
- metadata filtering과 relational data 통합
- source of truth 근접

Neo4j vector index를 검토하는 조건:

- graph traversal 직후 semantic neighborhood search가 latency상 유리
- duplicate vector storage 비용보다 query simplicity가 중요
- benchmark에서 pgvector 왕복보다 의미 있는 개선

---

# 13. API Contract

Graph API는 raw Cypher를 외부에 노출하지 않는다.

```http
GET /graph/dramas/{id}/neighbors?types=ACTED_IN,HAS_OST&depth=2
```

AI API 내부에는 제한된 graph query builder를 둔다.

MCP에서도 arbitrary Cypher 실행 tool은 제공하지 않는다.

---

# 14. Graph Security

- parameterized Cypher
- depth hard limit
- node limit
- timeout
- read-only graph account for query API
- write account only for materialization worker

---

# 15. Graph Quality Checks

```text
orphan node rate
edge count by type
canonical ID uniqueness
missing endpoint
unexpected degree spike
projection lag
```

작품 하나가 수만 배우와 연결되는 비정상 상황 등을 탐지한다.

---

# 16. References

- Neo4j Vector Indexes  
  https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/
- Neo4j Cypher Manual  
  https://neo4j.com/docs/cypher-manual/current/
- Microsoft GraphRAG  
  https://microsoft.github.io/graphrag/
