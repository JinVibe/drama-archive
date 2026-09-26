-- Reference data that the product treats as fixed taxonomy.
-- Broadcasters: docs/PRD.md §34 MVP 0. Genres: initial canonical set; extend via new migrations.

INSERT INTO broadcaster (code, name_ko, name_en, official_url) VALUES
    ('kbs',  'KBS',  'Korean Broadcasting System', 'https://www.kbs.co.kr'),
    ('mbc',  'MBC',  'Munhwa Broadcasting Corporation', 'https://www.imbc.com'),
    ('sbs',  'SBS',  'Seoul Broadcasting System', 'https://www.sbs.co.kr'),
    ('jtbc', 'JTBC', 'JTBC', 'https://www.jtbc.co.kr'),
    ('tvn',  'tvN',  'tvN', 'https://tvn.cjenm.com');

INSERT INTO genre (code, name_ko) VALUES
    ('romance',    '로맨스'),
    ('comedy',     '코미디'),
    ('melodrama',  '멜로'),
    ('fantasy',    '판타지'),
    ('thriller',   '스릴러'),
    ('mystery',    '미스터리'),
    ('crime',      '범죄'),
    ('action',     '액션'),
    ('medical',    '의학'),
    ('legal',      '법정'),
    ('historical', '사극'),
    ('family',     '가족'),
    ('youth',      '청춘'),
    ('office',     '오피스'),
    ('sf',         'SF'),
    ('horror',     '공포'),
    ('daily',      '일일');
