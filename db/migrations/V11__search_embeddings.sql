-- Semantic search (DM-601/602): dense embeddings on search_document.
-- Model: BAAI/bge-m3 (1024-dim, cosine). Changing the model means a new migration
-- that alters the dimension and a full re-embed (docs/AIRFLOW_DAGS.md §12).

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE search_document
    ADD COLUMN embedding             vector(1024),
    ADD COLUMN embedding_model       VARCHAR(100),
    ADD COLUMN embedding_updated_at  TIMESTAMPTZ;

-- HNSW over cosine distance. m/ef_construction are pgvector defaults; revisit with data.
CREATE INDEX idx_search_document_embedding_hnsw
    ON search_document USING hnsw (embedding vector_cosine_ops);

-- embedding_refresh DAG picks rows whose document changed after they were embedded.
CREATE INDEX idx_search_document_needs_embedding
    ON search_document (updated_at)
    WHERE embedding IS NULL OR embedding_updated_at < updated_at;
