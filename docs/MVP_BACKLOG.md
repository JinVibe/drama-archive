# MVP Backlog

## 1. Priority

- **P0**: 없으면 다음 단계가 성립하지 않음
- **P1**: MVP 가치 핵심
- **P2**: 품질/확장
- **P3**: 실험

---

# Epic 0 — Project Foundation

## DM-001 Monorepo skeleton — P0

Acceptance:

- `apps/web`
- `apps/domain-api`
- `apps/ai-api`
- `data-platform`
- `infra`
- `evals`
- local Docker Compose

## DM-002 CI — P0

Acceptance:

- lint
- unit test
- build
- migration check

## DM-003 OpenTelemetry baseline — P1

Acceptance:

- trace ID가 web → API까지 이어짐
- DB span 확인

---

# Epic 1 — Canonical Data Model

## DM-101 Core schema — P0

Drama/Person/Credit/Broadcaster/Genre.

## DM-102 OST schema — P0

Song/Artist/DramaOST.

## DM-103 Provenance — P0

모든 imported entity가 source_record로 추적 가능.

## DM-104 Admin review queue — P1

entity resolution ambiguity 확인/승인.

---

# Epic 2 — Airflow Data Platform

## DM-201 Airflow local stack — P0

## DM-202 Raw snapshot DAG — P0

Acceptance:

- fetch 결과 Object Storage 보관
- hash 기록

## DM-203 Normalize DAG — P0

## DM-204 Entity resolution — P0

## DM-205 Data quality gate — P0

## DM-206 Gold publish — P0

## DM-207 Link validator — P1

## DM-208 Backfill pipeline — P1

---

# Epic 3 — Public Archive

## DM-301 Year archive — P1

`/years/{year}`

## DM-302 Broadcaster archive — P1

## DM-303 Drama detail — P1

## DM-304 Actor detail — P1

## DM-305 OST section — P1

## DM-306 Official watch links — P1

## DM-307 SEO metadata/sitemap — P1

---

# Epic 4 — User Memory

## DM-401 Authentication — P1

[ADR-011](ADR/ADR-011-guest-first-auth.md) Guest-first.

Acceptance:

- 로그인 없이 봤어요 클릭 시 익명 `app_user` + 서명 쿠키 발급
- 카카오/네이버/구글 로그인으로 기존 익명 계정에 identity 연결 (기록 유지)
- 이미 연결된 provider면 §7 병합 규칙대로 합치고 익명 계정은 MERGED
- 필수 동의 3개(약관/처리방침/14세 이상)만, 마케팅은 선택. `user_consent`에 버전 기록
- `anonymous_user_cleanup` DAG: 90일 무활동 익명 계정 삭제
- 개인정보처리방침·이용약관 초안 `docs/legal/` (배포 전 필수)

## DM-402 Watched state — P1

## DM-403 Timeline — P1

## DM-404 Memory note — P1

private first.

## DM-405 Share card — P2

server-side generated image.

---

# Epic 5 — Search v1

## DM-501 Alias/FTS — P0

## DM-502 Search document projection — P0

## DM-503 Query analytics — P1

zero result/reformulation tracking.

---

# Epic 6 — Semantic Search

## DM-601 Embedding pipeline — P1

## DM-602 pgvector HNSW — P1

## DM-603 Metadata-aware vector query — P1

## DM-604 RRF fusion — P1

## DM-605 Reranker experiment — P2

---

# Epic 7 — AI Memory Search

## DM-701 Query schema extraction — P1

## DM-702 Query router — P1

## DM-703 Context builder — P1

## DM-704 Grounded generation — P1

## DM-705 Evidence UI — P1

## DM-706 Abstention/fallback — P1

---

# Epic 8 — Knowledge Graph

## DM-801 Neo4j local/prod config — P1

## DM-802 Graph materialization DAG — P1

## DM-803 Graph integrity test — P1

## DM-804 Actor collaboration query — P1

## DM-805 Drama/OST traversal — P1

## DM-806 Graph UI — P2

---

# Epic 9 — Evaluation

## DM-901 Golden query v1 — P0

최소 200 queries.

## DM-902 Retrieval runner — P0

Recall@K/MRR/NDCG.

## DM-903 Graph benchmark — P1

## DM-904 Regression report DAG — P1

## DM-905 Human bad-case review — P1

---

# Epic 10 — GraphRAG

전제:

- canonical graph 안정
- corpus provenance 확립
- baseline eval 존재

## DM-1001 Corpus policy — P0 for GraphRAG

## DM-1002 Corpus build DAG — P1

## DM-1003 GraphRAG index experiment — P2

## DM-1004 Local Search adapter — P2

## DM-1005 DRIFT experiment — P3

## DM-1006 Global Search experiment — P3

## DM-1007 Baseline comparison — P1

Acceptance:

GraphRAG 사용 query class를 eval로 명시한다.

---

# Epic 11 — MCP

## DM-1101 Remote MCP server — P2

2026-07-28 spec.

## DM-1102 Public catalog tools — P2

## DM-1103 Graph traversal tool — P2

## DM-1104 OAuth — P2

## DM-1105 Timeline protected tools — P3

## DM-1106 MCP observability — P2

---

# Epic 12 — Production Hardening

## DM-1201 IaC with OpenTofu — P1

## DM-1202 Secret management — P1

## DM-1203 Backup/restore test — P1

## DM-1204 Rate limit/WAF — P1

## DM-1205 Runbooks — P1

## DM-1206 Cost dashboard — P2

---

# Recommended Milestones

## M0 — Data Foundation

```text
DM-001~003
DM-101~104
DM-201~206
```

Definition of Done:

> 한 방송사의 작품 데이터가 raw snapshot부터 canonical DB까지 자동 반영된다.

## M1 — Usable Archive

```text
DM-301~307
DM-401~403
DM-501~503
```

Definition of Done:

> 연도별로 작품을 찾고, 상세를 보고, 봤어요를 체크할 수 있다.

## M2 — AI Search

```text
DM-601~605
DM-701~706
DM-901~902
```

Definition of Done:

> 모호한 기억 질의가 benchmark에서 측정된다.

## M3 — Graph

```text
DM-801~806
DM-903~904
```

## M4 — GraphRAG

```text
DM-1001~1007
```

## M5 — Agent Platform

```text
DM-1101~1106
DM-1201~1206
```

---

# What Not To Do First

다음은 첫 스프린트에서 하지 않는다.

- Kafka
- Kubernetes
- dedicated Vector DB
- multi-agent framework
- GraphRAG global search
- 실시간 recommendation stream
- 자체 LLM fine-tuning

데이터와 평가셋이 없으면 이런 기술을 넣어도 성능 개선을 증명할 수 없다.
