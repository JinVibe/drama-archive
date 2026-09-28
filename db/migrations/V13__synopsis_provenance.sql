-- Synopsis attribution. Text quoted from a licensed source (Korean Wikipedia, CC BY-SA 4.0)
-- must be shown with its source and license (PRD §28 copyright/legal).

ALTER TABLE drama
    ADD COLUMN synopsis_source      VARCHAR(30),   -- 'kowiki' | 'seed' | NULL (own text)
    ADD COLUMN synopsis_source_url  TEXT,
    ADD COLUMN synopsis_license     VARCHAR(40);   -- e.g. 'CC BY-SA 4.0'

-- Korean Wikipedia REST summaries (extract of the lead section).
INSERT INTO source (code, base_url, source_type, trust_level, terms_note, active) VALUES
    ('kowiki', 'https://ko.wikipedia.org', 'OPEN_DATA', 60,
     'Korean Wikipedia, CC BY-SA 4.0. Lead-section extracts only, always shown with attribution and license link. REST API: keep well under 200 req/s; descriptive User-Agent.', true);
