-- Search v1 (DM-501/502/503): lexical search documents + query analytics.
-- Source: docs/DATA_MODEL.md §10. Embedding columns arrive with DM-601 once the
-- embedding model (and therefore the vector dimension) is chosen.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Derived projection of canonical entities; rebuilt by the search_document_build DAG.
CREATE TABLE search_document (
    id                BIGSERIAL    PRIMARY KEY,
    entity_type       VARCHAR(30)  NOT NULL,       -- 'DRAMA' (PERSON later)
    entity_id         BIGINT       NOT NULL,
    title             TEXT         NOT NULL,       -- display title
    aliases           TEXT         NOT NULL DEFAULT '',   -- newline-separated alternative titles
    body              TEXT         NOT NULL,       -- rendered text: broadcaster, year, genres, cast, OST, synopsis
    metadata          JSONB        NOT NULL,       -- structured facets for filtering / result rendering
    document_version  BIGINT       NOT NULL DEFAULT 1,
    content_hash      VARCHAR(128) NOT NULL,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- 'simple' config: no stemming, tokens split on whitespace/punctuation. Korean
    -- has no stemmer in core PostgreSQL; trigram search below covers partial matches.
    fts tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(aliases, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(body, '')), 'B')
    ) STORED,

    UNIQUE (entity_type, entity_id),
    CONSTRAINT chk_search_document_entity_type CHECK (entity_type IN ('DRAMA', 'PERSON'))
);

CREATE INDEX idx_search_document_fts        ON search_document USING GIN (fts);
CREATE INDEX idx_search_document_title_trgm ON search_document USING GIN (title gin_trgm_ops);
CREATE INDEX idx_search_document_alias_trgm ON search_document USING GIN (aliases gin_trgm_ops);

-- Query analytics (DM-503). No user identifier is stored; only what was asked and what came back.
CREATE TABLE search_query_log (
    id                BIGSERIAL    PRIMARY KEY,
    query_raw         TEXT         NOT NULL,
    query_normalized  TEXT         NOT NULL,
    strategy          VARCHAR(30)  NOT NULL,       -- 'FTS', 'TRIGRAM', 'FUSED', 'NONE'
    result_count      INTEGER      NOT NULL,
    latency_ms        INTEGER,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_search_query_log_created ON search_query_log (created_at);
-- Zero-result queries are the main input for alias curation.
CREATE INDEX idx_search_query_log_zero ON search_query_log (created_at) WHERE result_count = 0;
