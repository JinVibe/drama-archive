-- Open-data collection (Wikidata) and the broadcasters/platforms it references.

ALTER TABLE source DROP CONSTRAINT chk_source_type;
ALTER TABLE source ADD CONSTRAINT chk_source_type
    CHECK (source_type IN ('BROADCASTER', 'OTT', 'EDITORIAL', 'MANUAL', 'OPEN_DATA'));

-- CC0; entity ids (Q-ids) are stable and become external ids for dramas and people.
INSERT INTO source (code, base_url, source_type, trust_level, terms_note, active) VALUES
    ('wikidata', 'https://query.wikidata.org', 'OPEN_DATA', 70,
     'Wikidata (CC0). Descriptive User-Agent required; keep to ~1 request/sec on the query service.', true);

-- Channels and platforms that carry Korean dramas but were not in the MVP five.
INSERT INTO broadcaster (code, name_ko, name_en, official_url) VALUES
    ('ocn',          'OCN',        'OCN',            'https://ocn.cjenm.com'),
    ('mbn',          'MBN',        'MBN',            'https://www.mbn.co.kr'),
    ('channel_a',    '채널A',       'Channel A',      'https://www.ichannela.com'),
    ('tv_chosun',    'TV조선',      'TV Chosun',      'https://tv.chosun.com'),
    ('ena',          'ENA',        'ENA',            'https://www.ena.co.kr'),
    ('mnet',         'Mnet',       'Mnet',           'https://www.mnet.com'),
    ('mbc_every1',   'MBC 에브리원', 'MBC every1',     'https://www.mbcplus.com'),
    ('ebs',          'EBS',        'EBS',            'https://www.ebs.co.kr'),
    ('netflix',      '넷플릭스',     'Netflix',        'https://www.netflix.com'),
    ('disney_plus',  '디즈니+',      'Disney+',        'https://www.disneyplus.com'),
    ('tving',        '티빙',        'TVING',          'https://www.tving.com'),
    ('wavve',        '웨이브',       'Wavve',          'https://www.wavve.com'),
    ('coupang_play', '쿠팡플레이',    'Coupang Play',   'https://www.coupangplay.com'),
    ('genie_tv',     '지니 TV',      'Genie TV',       'https://www.genie.co.kr'),
    ('kakao_tv',     '카카오TV',     'Kakao TV',       'https://tv.kakao.com'),
    ('naver_tv',     '네이버TV',     'Naver TV',       'https://tv.naver.com');
