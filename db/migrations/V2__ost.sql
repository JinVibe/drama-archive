-- OST model: song, artist, song_artist, drama_ost.
-- Source: docs/DATA_MODEL.md §4.

CREATE TABLE song (
    id                BIGSERIAL PRIMARY KEY,
    title             VARCHAR(255) NOT NULL,
    title_normalized  VARCHAR(255) NOT NULL,
    release_date      DATE,
    duration_seconds  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_song_duration
        CHECK (duration_seconds IS NULL OR duration_seconds > 0)
);

CREATE INDEX idx_song_title_normalized ON song (title_normalized);

CREATE TRIGGER trg_song_updated_at
    BEFORE UPDATE ON song
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE artist (
    id               BIGSERIAL PRIMARY KEY,
    name             VARCHAR(180) NOT NULL,
    name_normalized  VARCHAR(180) NOT NULL UNIQUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_artist_updated_at
    BEFORE UPDATE ON artist
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE song_artist (
    song_id     BIGINT      NOT NULL REFERENCES song(id) ON DELETE CASCADE,
    artist_id   BIGINT      NOT NULL REFERENCES artist(id),
    role        VARCHAR(30) NOT NULL DEFAULT 'PERFORMER',   -- 'PERFORMER', 'COMPOSER', 'LYRICIST', 'FEATURING'
    sort_order  INTEGER,
    PRIMARY KEY (song_id, artist_id, role)
);

CREATE INDEX idx_song_artist_artist ON song_artist (artist_id);

CREATE TABLE drama_ost (
    drama_id  BIGINT NOT NULL REFERENCES drama(id) ON DELETE CASCADE,
    song_id   BIGINT NOT NULL REFERENCES song(id),
    part_no   INTEGER,
    track_no  INTEGER,
    PRIMARY KEY (drama_id, song_id)
);

CREATE INDEX idx_drama_ost_song ON drama_ost (song_id);
