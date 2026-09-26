# Implementation Guide

## 1. 첫 구현 Vertical Slice

처음부터 모든 방송사를 긁지 않는다.

권장:

```text
tvN 1개 연도
→ 30~100 작품
→ 배우
→ OST
→ 공식 링크
```

이 데이터로 end-to-end를 먼저 완성한다.

```text
source
→ raw snapshot
→ normalize
→ canonical
→ web detail
→ FTS
→ embedding
→ graph
→ eval
```

이후 source를 늘린다.

---

## 2. Repo

```text
dramamemory/
├─ apps/
│  ├─ web/
│  ├─ domain-api/
│  ├─ ai-api/
│  └─ mcp-server/
├─ data-platform/
│  ├─ dags/
│  ├─ src/
│  │  ├─ collectors/
│  │  ├─ parsers/
│  │  ├─ normalization/
│  │  ├─ entity_resolution/
│  │  ├─ quality/
│  │  └─ graph/
│  └─ tests/
├─ evals/
├─ infra/
├─ docs/
└─ compose.yaml
```

---

## 3. Local Bring-up Order

```text
1. PostgreSQL + pgvector
2. migrations
3. Object Storage
4. Airflow
5. domain-api
6. web
7. Redis
8. ai-api
9. Neo4j
10. MCP
11. OTel
```

MCP는 가장 마지막이다.

---

## 4. First Demo Definition

데모 시나리오:

1. Airflow가 source에서 작품을 ingest
2. raw snapshot 저장
3. canonical DB 생성
4. `/years/2016` 표시
5. `/dramas/{slug}` 출연진/OST 표시
6. 사용자가 봤어요 체크
7. 자연어로 “2016년 겨울 공유 나온 판타지” 검색
8. 검색 trace에서 SQL/vector retrieval 확인
9. Neo4j에서 작품-배우-OST graph 탐색
10. evaluation report에서 baseline 대비 결과 확인

GraphRAG는 이 데모가 안정된 뒤 넣는다.

---

## 5. Portfolio Demo Extension

GraphRAG 추가 후:

> “도깨비 주변 작품 중 비슷한 시대의 판타지/로맨스 작품 관계를 배우 및 OST 연결과 함께 보여줘.”

화면에서는:

- 최종 답
- retrieved dramas
- graph path
- source
- retrieval strategy
- trace latency

를 개발자 모드에서 보여주면 기술 선택 이유가 잘 드러난다.

---

## 6. 기술을 추가할 때 질문

새 기술마다 아래 ADR 질문에 답한다.

```text
1. 지금 어떤 구체적 문제가 있는가?
2. 현재 방법의 측정된 한계는?
3. 새 기술은 어떤 metric을 개선해야 하는가?
4. 운영 비용은?
5. 제거 조건은?
```

다섯 개에 답하지 못하면 아직 도입할 단계가 아니다.
