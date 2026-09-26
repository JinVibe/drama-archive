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

첫 파이프라인 smoke test:

```sh
docker compose run --rm airflow-cli dags unpause ingest_source_records__manual
docker compose run --rm airflow-cli dags trigger ingest_source_records__manual
# 결과: source_record 행 1개 + 버킷 안 raw 스냅샷 1개. 다시 실행해도 늘어나지 않는다.
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

## 진행 상태

- [x] Phase 0 — canonical schema + provenance (`db/migrations` V1~V6)
- [ ] Phase 1 — Airflow ingestion + data quality
  - [x] DM-201 Airflow local stack
  - [x] DM-202 raw snapshot DAG (`ingest_source_records__{source}`)
  - [ ] DM-203 normalize · DM-204 entity resolution · DM-205 quality gate · DM-206 gold publish
- [ ] Phase 2 이후

## 현재 문서 기준

2026-09-26 기준으로 작성했다.

- Apache Airflow 3.3.x Asset/Event-driven scheduling
- Microsoft GraphRAG Local / Global / DRIFT / Basic search
- MCP Specification 2026-07-28
- pgvector HNSW / IVFFlat
- Neo4j Cypher 25 / 2026 vector index 계열
- OpenTelemetry traces/spans

상세 출처는 각 설계 문서의 References를 참고한다.
