-- Popularity proxy for "그해의 인기작" on the year pages. The catalog has no ratings,
-- so popularity_refresh_kowiki stores the Korean Wikipedia article's page views
-- over the trailing year (Wikimedia pageviews API, public). It is a proxy for
-- lasting interest, not a viewership figure, and the UI must say so.
ALTER TABLE drama
    ADD COLUMN popularity_score       NUMERIC(14, 2),
    ADD COLUMN popularity_source      VARCHAR(40),    -- 'kowiki:pageviews:365d'
    ADD COLUMN popularity_updated_at  TIMESTAMPTZ;

CREATE INDEX idx_drama_popularity ON drama (popularity_score DESC NULLS LAST)
    WHERE status = 'PUBLISHED';
