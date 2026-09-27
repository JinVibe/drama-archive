# ai-api

FastAPI AI Query Service: query analysis, lexical + vector retrieval, RRF fusion. Generation
(DM-704) and GraphRAG come later behind the same retrieval. See `docs/RAG_DESIGN.md`.

Owns no canonical writes. The only write it enables is `search_document.embedding`, and even
that is performed by the `embedding_refresh` Airflow DAG calling `/internal/embed`, so the
model lives in exactly one process.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/search?q=&size=&mode=hybrid\|lexical\|vector` | retrieval only; response carries the query plan, per-retriever candidate counts, per-hit ranks/scores, latency per stage, `retrieval_version`, `embedding_model`. `mode` exists for evaluation |
| POST | `/internal/embed` | `{texts[]}` -> vectors. `X-Internal-Token` header when `AI_API_INTERNAL_TOKEN` is set |
| GET | `/health/live`, `/health/ready` | ready only after the model is loaded |

## Retrieval

1. `retrieval/query.py` — deterministic constraint extraction: year / decade / "쯤" windows,
   broadcaster aliases; leftover text goes to retrievers. Swappable for an LLM extractor later.
2. `retrieval/store.py` — three candidate lists over `search_document`, all honoring the same
   filters: FTS (`websearch_to_tsquery`, simple), trigram (title/aliases), vector (pgvector cosine, HNSW).
3. `retrieval/fusion.py` — RRF (k=60). Raw scores are never added.

## Embeddings

`BAAI/bge-m3` (1024-dim, normalized) via sentence-transformers on CPU; weights are downloaded on
first start into the `hf-models` volume (`HF_HOME=/models`). `AI_API_EMBEDDER=fake` swaps in a
deterministic hash embedder for tests and CI. Changing the model = new migration (dimension) +
full re-embed.

## Run

```sh
pip install -e ".[dev]"            # unit tests need no torch and no database
pytest -q && ruff check .
docker compose up -d --build ai-api   # http://localhost:8090/docs
```
