-- The metadata-only vector (title, cast, year) measured as pure noise once the plot
-- had its own vector (RAG_DESIGN 구현 현황: AI_API_LIST_WEIGHTS=vector:0 since
-- 2026-09-28). Drop it: half the embedding work per document, one list fewer.
-- embedding_synopsis stays; a document without a plot simply has no vector and is
-- found through FTS / trigram / graph.

DROP INDEX IF EXISTS idx_search_document_embedding_hnsw;
DROP INDEX IF EXISTS idx_search_document_needs_embedding;
ALTER TABLE search_document DROP COLUMN embedding;

-- embedding_refresh picks rows whose document changed after they were last embedded.
CREATE INDEX idx_search_document_needs_embedding
    ON search_document (updated_at)
    WHERE embedding_updated_at IS NULL OR embedding_updated_at < updated_at;
