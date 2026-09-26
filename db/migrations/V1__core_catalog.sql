-- Core canonical catalog: broadcaster, genre, drama, person, credit, official links.
-- Source: docs/DATA_MODEL.md §3, §5, §6, §13.

-- Shared trigger to keep updated_at current on every UPDATE.
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- broadcaster
-- ---------------------------------------------------------------------------
CREATE TABLE broadcaster (
    id            BIGSERIAL PRIMARY KEY,
    code          VARCHAR(32)  NOT NULL UNIQUE,   -- 'kbs', 'mbc', 'sbs', 'jtbc', 'tvn'
    name_ko       VARCHAR(100) NOT NULL,
    name_en       VARCHAR(100),
    official_url  TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_broadcaster_updated_at
    BEFORE UPDATE ON broadcaster
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- genre (canonical taxonomy; unstructured themes are NOT stored here)
-- ---------------------------------------------------------------------------
CREATE TABLE genre (
    id       BIGSERIAL PRIMARY KEY,
    code     VARCHAR(50)  NOT NULL UNIQUE,
    name_ko  VARCHAR(100) NOT NULL
);

-- ---------------------------------------------------------------------------
-- drama
-- ---------------------------------------------------------------------------
CREATE TABLE drama (
    id                 BIGSERIAL PRIMARY KEY,
    slug               VARCHAR(180) NOT NULL UNIQUE,
    title_ko           VARCHAR(255) NOT NULL,
    title_en           VARCHAR(255),
    title_normalized   VARCHAR(255) NOT NULL,
    broadcaster_id     BIGINT REFERENCES broadcaster(id),
    start_date         DATE,
    end_date           DATE,
    episode_count      INTEGER,
    runtime_minutes    INTEGER,
    synopsis           TEXT,
    official_page_url  TEXT,
    -- Soft delete / lifecycle. External source removal never hard-deletes a row.
    status             VARCHAR(30) NOT NULL DEFAULT 'PUBLISHED',
    -- When status = 'MERGED', points at the surviving canonical row.
    merged_into_id     BIGINT REFERENCES drama(id),
    canonical_version  BIGINT NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_drama_status
        CHECK (status IN ('PUBLISHED', 'HIDDEN', 'DEPRECATED', 'MERGED')),
    CONSTRAINT chk_drama_merged_target
        CHECK ((status = 'MERGED') = (merged_into_id IS NOT NULL)),
    CONSTRAINT chk_drama_date_order
        CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date),
    CONSTRAINT chk_drama_episode_count
        CHECK (episode_count IS NULL OR episode_count > 0)
);

CREATE INDEX idx_drama_start_date       ON drama (start_date);
CREATE INDEX idx_drama_broadcaster      ON drama (broadcaster_id);
CREATE INDEX idx_drama_title_normalized ON drama (title_normalized);

CREATE TRIGGER trg_drama_updated_at
    BEFORE UPDATE ON drama
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE drama_alias (
    drama_id          BIGINT       NOT NULL REFERENCES drama(id) ON DELETE CASCADE,
    alias             VARCHAR(255) NOT NULL,
    alias_normalized  VARCHAR(255) NOT NULL,
    language_code     VARCHAR(16),
    alias_type        VARCHAR(30),                -- 'ORIGINAL', 'ENGLISH', 'ABBREVIATION', 'NICKNAME', ...
    PRIMARY KEY (drama_id, alias_normalized)
);

CREATE INDEX idx_drama_alias_normalized ON drama_alias (alias_normalized);

CREATE TABLE drama_genre (
    drama_id  BIGINT NOT NULL REFERENCES drama(id) ON DELETE CASCADE,
    genre_id  BIGINT NOT NULL REFERENCES genre(id),
    PRIMARY KEY (drama_id, genre_id)
);

-- ---------------------------------------------------------------------------
-- person (actors, directors, writers, ...)
-- ---------------------------------------------------------------------------
CREATE TABLE person (
    id                 BIGSERIAL PRIMARY KEY,
    slug               VARCHAR(180) NOT NULL UNIQUE,
    name_ko            VARCHAR(150) NOT NULL,
    name_en            VARCHAR(150),
    name_normalized    VARCHAR(150) NOT NULL,
    birth_date         DATE,
    status             VARCHAR(30) NOT NULL DEFAULT 'PUBLISHED',
    merged_into_id     BIGINT REFERENCES person(id),
    canonical_version  BIGINT NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_person_status
        CHECK (status IN ('PUBLISHED', 'HIDDEN', 'DEPRECATED', 'MERGED')),
    CONSTRAINT chk_person_merged_target
        CHECK ((status = 'MERGED') = (merged_into_id IS NOT NULL))
);

CREATE INDEX idx_person_name_normalized ON person (name_normalized);

CREATE TRIGGER trg_person_updated_at
    BEFORE UPDATE ON person
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- credit (drama <-> person)
-- ---------------------------------------------------------------------------
CREATE TABLE credit (
    id              BIGSERIAL PRIMARY KEY,
    drama_id        BIGINT       NOT NULL REFERENCES drama(id) ON DELETE CASCADE,
    person_id       BIGINT       NOT NULL REFERENCES person(id),
    credit_type     VARCHAR(30)  NOT NULL,        -- 'ACTOR', 'DIRECTOR', 'WRITER', 'PRODUCER'
    character_name  VARCHAR(150),
    billing_order   INTEGER,
    is_main_cast    BOOLEAN      NOT NULL DEFAULT false,

    CONSTRAINT chk_credit_type
        CHECK (credit_type IN ('ACTOR', 'DIRECTOR', 'WRITER', 'PRODUCER'))
);

-- NULLS NOT DISTINCT so a person credited without a character name is still unique per role.
CREATE UNIQUE INDEX uq_credit_role
    ON credit (drama_id, person_id, credit_type, character_name) NULLS NOT DISTINCT;

CREATE INDEX idx_credit_person ON credit (person_id, drama_id);
CREATE INDEX idx_credit_drama  ON credit (drama_id, billing_order);

-- ---------------------------------------------------------------------------
-- streaming_link (official watch links only; we never host media)
-- ---------------------------------------------------------------------------
CREATE TABLE streaming_link (
    id                   BIGSERIAL PRIMARY KEY,
    drama_id             BIGINT      NOT NULL REFERENCES drama(id) ON DELETE CASCADE,
    provider_code        VARCHAR(60) NOT NULL,     -- 'kbs', 'wavve', 'tving', 'netflix', ...
    url                  TEXT        NOT NULL,
    link_type            VARCHAR(30) NOT NULL,
    region_code          VARCHAR(10) NOT NULL DEFAULT 'KR',
    availability_status  VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN',
    http_status          INTEGER,
    last_verified_at     TIMESTAMPTZ,
    valid_from           TIMESTAMPTZ,
    valid_to             TIMESTAMPTZ,
    -- FK to source_record is added in the provenance migration.
    source_record_id     BIGINT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_streaming_link UNIQUE (drama_id, provider_code, url),
    CONSTRAINT chk_streaming_link_type
        CHECK (link_type IN ('OFFICIAL_VOD', 'BROADCASTER_PAGE', 'OTT_DETAIL', 'OFFICIAL_CLIP', 'OFFICIAL_OST')),
    CONSTRAINT chk_streaming_link_availability
        CHECK (availability_status IN (
            'AVAILABLE', 'REDIRECTED', 'NOT_FOUND', 'ACCESS_DENIED',
            'REGION_RESTRICTED', 'TEMPORARY_ERROR', 'UNKNOWN'))
);

CREATE INDEX idx_streaming_link_drama ON streaming_link (drama_id);

CREATE TRIGGER trg_streaming_link_updated_at
    BEFORE UPDATE ON streaming_link
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
