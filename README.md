# DramaMemory

> 내가 살아온 시절의 드라마를 다시 만나는 **한국 드라마 추억 아카이브 + AI 탐색 플랫폼**

DramaMemory는 KBS, MBC, SBS, JTBC, tvN 등 국내 방송사의 드라마를 연도·배우·OST·방송사·관계로 탐색하고, 사용자가 자신이 본 작품을 기록해 개인 드라마 연대기를 만들 수 있는 서비스다.

영상이나 음원을 직접 호스팅하지 않는다. 대신 정제된 메타데이터와 **공식 다시보기 링크**를 연결하고, 자연어 기억 검색·관계 검색·GraphRAG를 통해 “제목이 기억나지 않는 작품”까지 찾을 수 있게 한다.

## 기술적 핵심

- **Next.js**: SEO가 중요한 공개 탐색 UI
- **Spring Boot**: 사용자/시청기록/도메인 트랜잭션
- **FastAPI**: Hybrid RAG, GraphRAG, embedding, reranking
- **PostgreSQL**: System of Record
- **pgvector**: semantic retrieval
- **Neo4j**: multi-hop 관계 탐색 및 graph read model
- **Apache Airflow 3**: 수집·정제·인덱싱·그래프 동기화 오케스트레이션
- **Object Storage**: 원본 스냅샷 및 재처리 기반
- **Redis**: hot cache / AI response cache
- **MCP 2026-07-28**: 외부 AI Agent용 표준 인터페이스
- **OpenTelemetry**: API → Retrieval → LLM end-to-end tracing
- **OpenTofu**: Infrastructure as Code

## 설계 원칙

1. PostgreSQL이 canonical source of truth다.
2. Vector index와 graph는 언제든 재생성 가능한 derived state다.
3. LLM이 필요 없는 문제에는 LLM을 호출하지 않는다.
4. 정확한 관계는 DB가 책임지고, GraphRAG는 비정형 의미 관계를 보강한다.
5. 검색 전략은 SQL / lexical / vector / graph를 질의에 따라 선택한다.
6. 서로 다른 검색 점수는 raw score 합산 대신 우선 **RRF(Reciprocal Rank Fusion)** 로 결합한다.
7. Airflow는 online request path에 들어오지 않는다.
8. MCP는 내부 REST API를 대체하지 않는다.
9. 최신 기술은 “도입 이유 + 제거 조건”까지 문서화한다.
10. 모델·embedding·prompt 변경은 평가 결과 없이 배포하지 않는다.

## 문서

| 문서 | 내용 |
|---|---|
| [PRD](docs/PRD.md) | 제품 요구사항 |
| [Architecture](docs/ARCHITECTURE.md) | 전체 시스템 구조 |
| [Data Model](docs/DATA_MODEL.md) | PostgreSQL/검색 데이터 모델 |
| [Airflow DAGs](docs/AIRFLOW_DAGS.md) | 수집·변환·인덱싱 파이프라인 |
| [RAG Design](docs/RAG_DESIGN.md) | Hybrid RAG / GraphRAG 설계 |
| [Graph Model](docs/GRAPH_MODEL.md) | Neo4j 그래프 모델 |
| [MCP Spec](docs/MCP_SPEC.md) | MCP tools/resources/auth |
| [Evaluation](docs/EVALUATION.md) | Retrieval/Generation 평가 |
| [MVP Backlog](docs/MVP_BACKLOG.md) | 구현 순서와 Acceptance Criteria |
| [ADRs](docs/ADR/) | 주요 기술 의사결정 |

## 권장 구현 순서

```text
Phase 0  Canonical DB + provenance
Phase 1  Airflow ingestion + data quality
Phase 2  공개 아카이브 + watched timeline
Phase 3  FTS + pgvector Hybrid Search
Phase 4  Neo4j + graph query
Phase 5  GraphRAG + offline evaluation
Phase 6  MCP + observability + production hardening
```

GraphRAG, MCP, Neo4j가 앞 단계의 데이터 품질보다 먼저 나오지 않는다. 이 프로젝트에서 가장 중요한 기반은 **정확한 canonical entity와 source provenance**다.

## 로컬 개발

요구사항: Docker Desktop, GNU make (선택).

```sh
cp .env.example .env
make up            # postgres(pgvector) + flyway 마이그레이션 + redis + object storage(RustFS) + 버킷 생성
make airflow-up    # Airflow 3 (http://localhost:8080, 로컬은 로그인 없음)
make test-data     # data-platform ruff + pytest (Airflow 이미지 안에서 실행)
make dag-check     # DAG import 오류 검사 (CI와 동일)
make down          # 중지 / make clean 은 볼륨까지 삭제
```

첫 end-to-end (raw → silver → gold):

```sh
for d in ingest_source_records__local_seed normalize_catalog entity_resolution publish_gold_catalog; do
  docker compose run --rm airflow-cli dags unpause $d
done
docker compose run --rm airflow-cli dags trigger ingest_source_records__local_seed
# ingest가 끝나면 normalize → entity_resolution → publish가 asset으로 연쇄 실행된다.
# 결과: data-platform/seed/dramas/*.json 3편이 drama/person/credit/song/artist 테이블에 들어가고,
#       source_entity_map에 provenance, outbox_event에 DRAMA_CANONICAL_CREATED가 남는다.
# seed 파일을 고쳐 다시 trigger하면 external_ref로 같은 행에 매핑되어 canonical_version만 오른다.
```

디렉터리:

```text
apps/            web · domain-api · ai-api · mcp-server (아직 placeholder)
data-platform/   Airflow DAG + 파이프라인 코드 + 테스트
db/migrations/   Flyway 마이그레이션 (canonical schema)
evals/           평가 데이터셋/러너
infra/           IaC (별도 관리)
docs/            설계 문서
```

## 정적 배포 (GitHub Pages)

서버 없이 카탈로그만 보여 주는 데모: <https://jinvibe.github.io/drama-archive/>

```sh
make up && make airflow-up            # 로컬 스택 (domain-api :8081, ai-api :8090)
apps/web/scripts/deploy-pages.sh      # 정적 빌드(Docker) → gh-pages 브랜치 push
DRY_RUN=1 apps/web/scripts/deploy-pages.sh   # 빌드만 (apps/web/out)
```

`STATIC_EXPORT=1`이면 Next가 `output: export`로 연도·작품·인물 페이지 전부를 미리 렌더링한다. 검색은 브라우저 안에서(`public/search-index.json` + MiniSearch), 봤어요/추억 한 줄은 그 브라우저의 localStorage에만 저장된다. 관리자·공유 카드·AI 기억 검색·그래프 갱신은 서버 배포에서만 동작한다. 처음 한 번은 저장소 Settings → Pages → Source: **gh-pages / root**를 켜야 한다.

## 진행 상태

- [x] Phase 0 — canonical schema + provenance (`db/migrations` V1~V6)
- [x] Phase 1 — Airflow ingestion + data quality (M0 DoD 충족: raw snapshot → canonical DB 자동 반영)
  - [x] DM-201 Airflow local stack
  - [x] DM-202 raw snapshot DAG (`ingest_source_records__{source}`)
  - [x] DM-203 `normalize_catalog` · DM-204 `entity_resolution` · DM-205/206 `publish_gold_catalog`
  - [x] DM-104 admin review queue — `/admin/review` (병합/새로 만들기), `/admin/problems`, `ADMIN_TOKEN` 게이트, publish DAG asset-or-15분 스케줄
  - [x] DM-207 link validator (`official_link_validator` DAG; 링크 소스가 아직 없어 검증 대상 0) · [ ] DM-208 backfill
  - [ ] 실제 방송사 collector/parser (약관 확인 후) — 지금은 curated `dramamemory.drama.v1` JSON만
- [x] Phase 2 / M1 — 공개 아카이브 + watched timeline + 검색 v1 (M1 DoD 충족)
  - [x] `apps/domain-api` Spring Boot 4 / Java 17 — 공개 read API, `/me/*` (watched, note, timeline), `/search`
  - [x] DM-401 익명 세션(서명 쿠키) + identity 연결/병합 서비스 + 90일 정리 DAG · DM-402 watched · DM-403 timeline 집계 · DM-404 memory note(private)
  - [x] `apps/web` Next.js 16 — `/`, `/years/{year}`, `/dramas/{slug}`, `/persons/{slug}`, `/my`, `/search`, sitemap/robots, JSON-LD, OG 이미지, 봤어요/추억 한 줄, DM-405 share card
  - [x] DM-501/502/503 — `search_document` projection DAG, FTS + pg_trgm **RRF** 검색, zero-result 질의 로그
  - [ ] DM-401 카카오/네이버/구글 OAuth 콜백 (provider 앱 등록 후)
- [ ] Phase 3 / M2 — pgvector Hybrid Search + AI memory search (`apps/ai-api`) + golden query 평가
  - [x] DM-601/602 V11 `embedding vector(1024)` + HNSW, `embedding_refresh` DAG (search.documents asset → ai-api `/internal/embed`, 배치 체크포인트)
  - [x] `apps/ai-api` FastAPI — BGE-M3 로컬 임베딩, 질의 분석(연도/연대/쯤/방송사 → 필터), FTS+trigram+vector **RRF**, `/v1/search?mode=hybrid|lexical|vector`
  - [x] DM-901/902 `evals/retrieval` 골든 질의셋(120개, 7 클래스) + 러너(Recall@K/MRR/NDCG, 클래스별, 회귀 게이트) — 24편 기준 hybrid recall@5 0.99 / MRR 0.97 vs lexical 0.55 / 0.56 (`evals/retrieval/reports/latest.json`)
  - [x] seed 24편 (tvN 2016 전편 + KBS/SBS/MBC/JTBC 10편, **공식 출처 검증 전 초안**) · ER 동명이인(김원석 PD/작가) 리뷰 큐 → 수동 결정으로 검증
  - [x] web `/search` → ai-api hybrid, ai-api 장애 시 domain-api lexical로 degrade
  - [ ] DM-605 reranker 실험 · DM-701~706 AI memory search(LLM 생성·근거 UI·abstention) · 카탈로그 확대 후 골든셋 200+
- [ ] Phase 4 / M3 — Neo4j graph
  - [x] DM-801 Neo4j 2026.01 compose + Airflow 이미지(neo4j 드라이버) · DM-802 `graph_materialization` DAG(per-aggregate replace, 멱등) · DM-803 integrity test
  - [x] DM-804/805 ai-api `/v1/graph/*` (공동출연·작품 이웃·OST 가수 경유) + retrieval `graph` 리스트(RRF) · DM-806 작품/인물 페이지 관계 섹션
  - 측정: 24편에선 효과 없음 → 2,347편에서 multi_hop recall@1 0.71→0.96, MRR 0.81→1.00으로 유지 조건 충족(GRAPH_MODEL 구현 현황)
- [x] 카탈로그 확대 — **Wikidata(CC0) 수집기**: 2006년 이후 한국 드라마를 SPARQL ∪ 한국어 위키백과 연도별 드라마 분류에서 발견(2,838건) → **1,981편 발행**(KBS 607 · MBC 464 · SBS 393 · tvN 294 · JTBC 168 · 넷플릭스 94 · 디즈니+ 38, 2006년 이후; 비드라마 267·방송 예정 14·범위 밖 733은 HIDDEN, 사유 기록), 인물 2,453+(생년월일 91%), seed 24편 중 21편 자동 병합. `source_discovery_wikidata`(주간) → `ingest_source_records__wikidata`(청크 매핑, 풀 3슬롯 × 1 req/s) → 기존 체인
  - 검색 재측정(손으로 쓴 132질의): lexical recall@5 0.47 → **hybrid 0.91 / MRR 0.83** (RAG_DESIGN 구현 현황). 리뷰 큐 71 → ER 재해소로 44(사람당 1회 결정)
  - [x] 줄거리 — `synopsis_enrich_kowiki` DAG: 한국어 위키백과 요약(CC BY-SA 4.0, 출처·라이선스 표기) 약 94% 채움, semantic_memory recall@5 0.81 → 1.00 · 리뷰 큐 44 → 1(사람당 1회 결정 + 빈 별칭 버그 수정) → 재수집 후 10
  - [x] 데이터 생성 골든셋 300질의(`generate_golden.py`, 1,981편 기준) — hybrid recall@5 0.981 / MRR 0.943, graph 리스트 효과 재확인(multi_hop MRR 0.26 → 0.94)
  - [x] **드라마/비드라마 판정** — Wikidata "television series"에 섞인 예능·리얼리티(《런닝맨》, 《스트릿댄스 걸스 파이터》)를 `program_kind`(클래스·장르·kowiki 분류 규칙)로 걸러 발행분 190편 HIDDEN, 발견 단계에서 1,713건 제외. 목록 문서·단막극(episode 클래스) 규칙은 첫 실행이 잡아내 수정
  - [x] 방송 예정작 제외 — 시작일이 미래면 HIDDEN(`hidden_reason='upcoming'`, V16), 방영일에 자동 복귀
  - [x] **채널 범위** — KBS·MBC·SBS·tvN·JTBC + **넷플릭스·디즈니+ 오리지널**(방송사 방영이 없는 작품만; 파서가 P449에 방송사와 OTT가 함께 있으면 방송사를 택하므로 플랫폼 채널 = 오리지널). 다른 채널·채널 미상은 `out_of_scope`로 HIDDEN, `DRAMAMEMORY_SCOPE_BROADCASTERS`를 넓히면 자동 복귀
  - [x] 채널 추론 — Wikidata에 방송사가 없는 작품은 kowiki 분류("SBS 금토드라마")에서 추론(V15 provenance), 81편
  - [x] 줄거리 분리 — V14 `synopsis` 필드(fts weight C) + 별도 임베딩. 측정 결과 메타데이터 전용 벡터 리스트는 잡음이라 기본 `AI_API_LIST_WEIGHTS=vector:0`(recall@1 0.59 → 0.74, 범위 제한 후 0.77)
  - [x] DM-605 reranker 실험 — `AI_API_RERANKER=bge` + `?rerank=true`(bge-reranker-v2-m3): recall@1 0.77 → 0.84, MRR 0.84 → 0.89(semantic_memory·OST top-1 크게 개선)지만 CPU에서 **질의당 20초** → 기본 꺼짐, 채택 조건은 RAG_DESIGN(GPU/경량 모델 + 조건 질의 우회)
  - [x] **그해의 인기작** — 연도 페이지 상단에 5편. 시청률 데이터가 없어 `popularity_refresh_kowiki` DAG(주간)가 한국어 위키백과 문서 최근 1년 조회수(V19)를 대리 지표로 저장하고, UI에 "위키백과 조회수 기준"으로 표기
  - [x] **OST 소스** — `ost_enrich_kowiki` DAG: 한국어 위키백과 문서의 OST 섹션(`{{음반 정보}}`/`{{곡 목록}}`·표)을 파싱해 song/artist/drama_ost에 provenance와 함께 기록. 1,926편 중 **203편에 2,298곡·아티스트 977명**(나머지 문서엔 OST 섹션이 없음 — 소스의 한계). 연주곡·score cue 제외, 재실행 시 같은 곡에 매핑(합성 external id). seed 24편의 손으로 적은 OST 초안은 이 소스로 대체
  - [x] 리뷰 큐 10 → 0 — 남은 6건은 모두 "같은 소스가 다른 ID로 아는 동명이인/동명작품"이라 규칙화(`_distinct_by_source`): 이후 같은 유형은 리뷰 없이 새 행
  - [ ] 파싱 실패 잔여(제목 없는 항목 7) · `embedding` 컬럼 제거 · 범위 밖 채널은 요청 시 `DRAMAMEMORY_SCOPE_BROADCASTERS`로 확장
  - [ ] DM-903 graph benchmark 확대 · collaboration score · Character/Platform 노드
- [x] Phase 6 일부 — **`apps/mcp-server`**: MCP 2026-07-28 stateless streamable HTTP, 공개 tools 6종 + resources 4종 + prompts 2종(MCP_SPEC 구현 현황). 보호 도구는 OAuth 전까지 미등록
  - [ ] OpenTelemetry · 운영 하드닝(Phase 6 나머지)

## 현재 문서 기준

2026-09-26 기준으로 작성했다.

- Apache Airflow 3.3.x Asset/Event-driven scheduling
- Microsoft GraphRAG Local / Global / DRIFT / Basic search
- MCP Specification 2026-07-28
- pgvector HNSW / IVFFlat
- Neo4j Cypher 25 / 2026 vector index 계열
- OpenTelemetry traces/spans

상세 출처는 각 설계 문서의 References를 참고한다.
