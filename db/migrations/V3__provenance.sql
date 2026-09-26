-- Provenance: every imported canonical entity is traceable to a source record
-- and a raw snapshot in object storage.
-- Source: docs/DATA_MODEL.md §8, §9.

CREATE TABLE source (
    id           BIGSERIAL PRIMARY KEY,
    code         VARCHAR(60) NOT NULL UNIQUE,     -- 'kbs_official', 'tvn_official', ...
    base_url     TEXT,
    source_type  VARCHAR(30) NOT NULL,            -- 'BROADCASTER', 'OTT', 'EDITORIAL', 'MANUAL'
    trust_level  SMALLINT    NOT NULL,            -- higher wins on conflicting fields
    terms_note   TEXT,                            -- usage terms / crawl policy notes
    active       BOOLEAN     NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_source_type
        CHECK (source_type IN ('BROADCASTER', 'OTT', 'EDITORIAL', 'MANUAL')),
    CONSTRAINT chk_source_trust_level
        CHECK (trust_level BETWEEN 0 AND 100)
);

CREATE TRIGGER trg_source_updated_at
    BEFORE UPDATE ON source
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- One row per fetched payload. Same (source, entity, external_id, content_hash)
-- is never stored twice — this is the ingestion idempotency key.
CREATE TABLE source_record (
    id              BIGSERIAL PRIMARY KEY,
    source_id       BIGINT       NOT NULL REFERENCES source(id),
    external_id     VARCHAR(255),
    entity_type     VARCHAR(30)  NOT NULL,        -- 'DRAMA', 'PERSON', 'SONG', 'LINK'
    source_url      TEXT         NOT NULL,
    object_key      TEXT,                          -- raw snapshot key in object storage
    content_hash    VARCHAR(128),
    fetched_at      TIMESTAMPTZ  NOT NULL,
    parser_version  VARCHAR(80),
    raw_metadata    JSONB,

    CONSTRAINT chk_source_record_entity_type
        CHECK (entity_type IN ('DRAMA', 'PERSON', 'SONG', 'LINK'))
);

CREATE UNIQUE INDEX uq_source_record_content
    ON source_record (source_id, entity_type, external_id, content_hash) NULLS NOT DISTINCT;

CREATE INDEX idx_source_record_fetched_at ON source_record (fetched_at);

-- Links a source record to the canonical entity it contributed to,
-- with how the match was decided and how confident it was.
CREATE TABLE source_entity_map (
    id                BIGSERIAL PRIMARY KEY,
    source_record_id  BIGINT       NOT NULL REFERENCES source_record(id),
    canonical_type    VARCHAR(30)  NOT NULL,      -- 'DRAMA', 'PERSON', 'SONG', 'ARTIST'
    canonical_id      BIGINT       NOT NULL,
    match_method      VARCHAR(50)  NOT NULL,      -- 'EXTERNAL_ID', 'DETERMINISTIC', 'SCORED', 'MANUAL'
    decision          VARCHAR(30)  NOT NULL,      -- 'AUTO_MERGE', 'REVIEW', 'CREATE_NEW'
    confidence        NUMERIC(5,4),
    reviewed_by       UUID,
    reviewed_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT chk_source_entity_map_canonical_type
        CHECK (canonical_type IN ('DRAMA', 'PERSON', 'SONG', 'ARTIST')),
    CONSTRAINT chk_source_entity_map_decision
        CHECK (decision IN ('AUTO_MERGE', 'REVIEW', 'CREATE_NEW')),
    CONSTRAINT chk_source_entity_map_confidence
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);

CREATE INDEX idx_source_entity_map_canonical
    ON source_entity_map (canonical_type, canonical_id);
CREATE INDEX idx_source_entity_map_record
    ON source_entity_map (source_record_id);
-- Admin review queue: unresolved matches awaiting a human decision.
CREATE INDEX idx_source_entity_map_review
    ON source_entity_map (created_at) WHERE decision = 'REVIEW' AND reviewed_at IS NULL;

-- Official links carried the column from V1; wire the FK now that the target exists.
ALTER TABLE streaming_link
    ADD CONSTRAINT fk_streaming_link_source_record
    FOREIGN KEY (source_record_id) REFERENCES source_record(id);
