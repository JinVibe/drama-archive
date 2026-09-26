-- Ingestion sources. Must stay in sync with data-platform/src/dramamemory_data/sources.py.

INSERT INTO source (code, base_url, source_type, trust_level, terms_note, active) VALUES
    ('manual', NULL, 'MANUAL', 50,
     'Hand-curated manifests. URLs chosen by a maintainer; still only official pages.', true),
    ('tvn_official', 'https://tvn.cjenm.com', 'BROADCASTER', 90,
     'Official broadcaster site. Confirm robots.txt and terms before enabling automated discovery.', true);
