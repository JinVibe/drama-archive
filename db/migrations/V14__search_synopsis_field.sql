-- Synopsis as its own search field (docs/RAG_DESIGN.md 구현 현황, "줄거리 추가 전후").
-- Mixed into body/embedding, the plot text diluted cast and year signals
-- (person recall@5 0.93 -> 0.87 without graph). Now:
--   * fts: title/aliases A, body (channel, year, genres, cast, crew, OST) B, synopsis C
--   * two embeddings: `embedding` over title+aliases+body, `embedding_synopsis` over
--     title+synopsis; ai-api fuses them as two RRF lists.
-- search_document_build re-renders every document (DOCUMENT_VERSION 2) and
-- embedding_refresh re-embeds both columns.

ALTER TABLE search_document
    ADD COLUMN synopsis           TEXT NOT NULL DEFAULT '',
    ADD COLUMN embedding_synopsis vector(1024);

-- Generated columns cannot be altered in place: drop and recreate with the new weights.
DROP INDEX IF EXISTS idx_search_document_fts;
ALTER TABLE search_document DROP COLUMN fts;
ALTER TABLE search_document
    ADD COLUMN fts tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(aliases, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(body, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(synopsis, '')), 'C')
    ) STORED;
CREATE INDEX idx_search_document_fts ON search_document USING GIN (fts);

CREATE INDEX idx_search_document_embedding_synopsis_hnsw
    ON search_document USING hnsw (embedding_synopsis vector_cosine_ops);
