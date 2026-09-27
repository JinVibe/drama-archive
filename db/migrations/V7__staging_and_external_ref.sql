-- Silver layer: one normalized record per raw source_record, plus the nested-entity
-- external reference needed to match persons/songs embedded inside a drama record.
-- Source: docs/AIRFLOW_DAGS.md §6-§9, docs/PRD.md §13 (Silver).

CREATE TABLE staging_record (
    id                BIGSERIAL PRIMARY KEY,
    source_record_id  BIGINT       NOT NULL UNIQUE REFERENCES source_record(id),
    entity_type       VARCHAR(30)  NOT NULL,
    parser_version    VARCHAR(80)  NOT NULL,
    -- Normalized payload (dramamemory_data.normalization.models). NULL only on PARSE_FAILED.
    payload           JSONB,
    status            VARCHAR(30)  NOT NULL DEFAULT 'NEW',
    -- Entity-resolution output keyed by nested entity (see entity_resolution.matching).
    resolution        JSONB,
    -- Parse errors / quality issues. Dead-letter data lives here, not in retries.
    issues            JSONB,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT chk_staging_record_status
        CHECK (status IN ('NEW', 'PARSE_FAILED', 'RESOLVED', 'REVIEW', 'REJECTED', 'PUBLISHED')),
    CONSTRAINT chk_staging_record_payload
        CHECK ((status = 'PARSE_FAILED') OR (payload IS NOT NULL))
);

CREATE INDEX idx_staging_record_status ON staging_record (status, id);

CREATE TRIGGER trg_staging_record_updated_at
    BEFORE UPDATE ON staging_record
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- A drama record embeds its cast and OST. Those nested entities carry their own
-- external ids within the source; remember them so re-ingests match deterministically.
ALTER TABLE source_entity_map
    ADD COLUMN external_ref VARCHAR(255);

CREATE INDEX idx_source_entity_map_external_ref
    ON source_entity_map (canonical_type, external_ref)
    WHERE external_ref IS NOT NULL;

-- Local-only source: nginx serving data-platform/seed/ inside compose.
INSERT INTO source (code, base_url, source_type, trust_level, terms_note, active) VALUES
    ('local_seed', 'http://seed:8000', 'MANUAL', 50,
     'Curated dramamemory.drama.v1 JSON served from the repo. Local development only.', true);
