# Evaluation Plan

## 1. 목표

AI 검색의 품질을 “데모가 잘 됨”으로 평가하지 않는다.

평가를 네 층으로 나눈다.

```text
Data Quality
Retrieval Quality
Answer Quality
Product Outcome
```

---

# 2. Golden Dataset

초기 최소 200~500개의 사람이 검증한 query를 만든다.

구성:

| Class | 예 |
|---|---|
| Exact | 도깨비 |
| Alias/typo | 태양 후예 |
| Structured | 2016 tvN 드라마 |
| Semantic | 겨울 느낌 판타지 로맨스 |
| Entity | 공유 나온 드라마 |
| Multi-hop | 공유와 이동욱 같이 나온 작품 OST |
| Temporal | 2014~2016 SBS 의학 드라마 |
| Global/theme | 2010년대 가족 드라마 경향 |

각 query:

```json
{
  "query_id": "q-001",
  "query": "아이유 호텔 드라마",
  "class": "semantic_memory",
  "relevant_drama_ids": [123],
  "graded_relevance": {"123": 3},
  "required_facts": ["actor:아이유", "setting:hotel"],
  "notes": ""
}
```

---

# 3. Retrieval Metrics

## Recall@K

정답 후보가 top K에 들어왔는지.

가장 중요한 초기 metric.

## Precision@K

특히 broad recommendation query.

## MRR

정답이 얼마나 앞에 나오는지.

## NDCG

graded relevance가 존재할 때.

## Route Accuracy

Query Router가 적절한 retrieval strategy를 선택했는지.

---

# 4. Retrieval Experiment Matrix

비교:

```text
A. SQL/FTS only
B. Vector only
C. FTS + Vector RRF
D. C + metadata filter
E. D + graph candidates
F. E + reranker
G. F + GraphRAG for eligible class
```

하나씩 추가해 incremental gain을 측정한다.

---

# 5. Graph Query Benchmark

multi-hop 전용 dataset을 별도 관리한다.

예:

```text
Q: A와 B가 같이 출연한 작품의 OST 가수
Expected path:
Person A → Drama ← Person B
Drama → Song ← Artist
```

metrics:

- path correctness
- final entity recall
- query latency
- graph node expansion count

---

# 6. GraphRAG Evaluation

query class별 비교:

```text
vector-only
canonical graph + vector
GraphRAG Local
GraphRAG DRIFT
GraphRAG Global
```

평가:

- factual coverage
- groundedness
- relation correctness
- latency
- token cost
- index cost

GraphRAG가 품질을 개선해도 비용이 과도하면 특정 기능에서만 사용한다.

---

# 7. Generation Metrics

## Groundedness

답변의 사실이 retrieval evidence에 존재하는가.

## Citation Consistency

표시된 source가 실제 claim을 뒷받침하는가.

## Factual Correctness

gold facts와 비교.

## Completeness

사용자 질문의 필수 슬롯을 충족했는가.

## Abstention Quality

근거가 없을 때 억지 답을 만들지 않는가.

---

# 8. Official Link Evaluation

특히 중요.

metric:

```text
valid_link_rate
stale_link_rate
wrong_drama_link_rate
provider_mismatch_rate
verification_age
```

AI answer가 공식 링크를 hallucinate하면 치명적이므로 URL 생성은 금지한다.

---

# 9. Entity Resolution Evaluation

labelled pair dataset:

```text
same_entity = true/false
```

metrics:

- precision
- recall
- false merge rate
- false split rate

우선순위:

> false merge를 false split보다 더 비싸게 본다.

잘못 합친 canonical entity는 graph 전체를 오염시킨다.

---

# 10. Data Quality Metrics

```text
null_title_rate
orphan_credit_rate
duplicate_drama_rate
unknown_broadcaster_rate
invalid_date_rate
source_freshness
parser_failure_rate
```

---

# 11. Online Product Metrics

검색 이후:

- click-through to drama
- search reformulation rate
- zero-result rate
- official watch link CTR
- watched conversion
- repeat search
- timeline creation

AI metric이 높아도 product metric이 나쁘면 기능을 재검토한다.

---

# 12. A/B Experiment

예:

```text
Control: FTS + Vector RRF
Treatment: + Graph candidate
```

측정:

```text
successful_click
time_to_first_relevant_click
reformulation
latency
```

초기 traffic이 작으면 통계적으로 과장하지 않고 offline evaluation을 중심으로 판단한다.

---

# 13. LLM-as-Judge

보조 수단으로만 사용한다.

원칙:

- deterministic metric 우선
- human-labeled subset 유지
- judge prompt/version 기록
- 동일 model family 편향 고려
- 중요한 correctness는 사람 검토

---

# 14. Regression Gate

production candidate마다:

```text
Recall@10 >= baseline - tolerance
MRR >= baseline - tolerance
groundedness >= threshold
wrong_link_rate == 0 on golden set
p95 latency <= budget
cost/query <= budget
```

threshold는 첫 benchmark 후 확정.

---

# 15. Evaluation Artifacts

```text
evals/
├─ datasets/
│  ├─ retrieval_v1.jsonl
│  ├─ graph_v1.jsonl
│  └─ entity_resolution_v1.jsonl
├─ runners/
├─ reports/
│  └─ 2026-09-26/
└─ configs/
```

---

# 16. Experiment Tracking

최소 기록:

```text
git_sha
dataset_version
canonical_snapshot
embedding_model
embedding_params
index_params
route_version
reranker
graphrag_version
prompt_version
llm_model
metrics
cost
```

MLflow/W&B는 실험 수가 실제로 많아질 때 도입할 수 있다. 처음에는 DB + artifact JSON도 충분하다.

---

# 17. Failure Review

매주 bad cases를 분류한다.

```text
data missing
entity resolution error
router error
lexical failure
embedding failure
graph missing edge
reranker error
generation hallucination
stale link
```

평가 목적은 모델 점수 자랑이 아니라 **실패 원인을 어느 계층에서 고쳐야 하는지 찾는 것**이다.
