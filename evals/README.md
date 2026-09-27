# evals

Golden query datasets and evaluation runners. See `docs/EVALUATION.md`.

## retrieval/ (DM-901 / DM-902)

- `golden_queries.jsonl` — one query per line: `{id, class, query, expected: [drama slugs]}`.
  Classes: `entity_lookup`, `person`, `character`, `ost`, `semantic_memory`, `temporal`, `genre`.
  Grows with the catalog; the target is 200+ once more than a handful of dramas exist.
- `run.py` — runs every query against one or more retrieval endpoints and prints/writes
  Recall@K, MRR, NDCG@K overall and per class, plus the failures. Stdlib only.
- `reports/` — JSON reports (`latest.json` committed as the current baseline).

```sh
# lexical baseline (domain-api) vs hybrid and vector (ai-api)
python evals/retrieval/run.py \
  --target lexical=http://localhost:8081/api/v1/search \
  --target hybrid="http://localhost:8090/v1/search?mode=hybrid" \
  --target vector="http://localhost:8090/v1/search?mode=vector" \
  --out evals/retrieval/reports/latest.json

# regression gate (docs/AIRFLOW_DAGS.md §16): fail when recall@5 drops below a floor
python evals/retrieval/run.py --target hybrid=... --min-recall5 0.9
```

Rule (README principle 10): no embedding/model/prompt change ships without a report showing
it did not regress the classes it is meant to improve.
